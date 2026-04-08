import json
import os
import sys
import shutil
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from skills.common.scripts.utils import build_feishu_url

def get_level(cred: str) -> int:
    if cred.startswith("L") and cred[1:].isdigit():
        return int(cred[1:])
    return 99

def match_company(text: str, companies: list) -> str:
    for c in companies:
        if c.get("name", "") in text or c.get("id", "") in text:
            return c["id"].lower()
        for alias in c.get("aliases", []):
            if alias in text:
                return c["id"].lower()
    return ""

def get_company(segments: list, filename: str, companies: list) -> str:
    for seg in reversed(segments):
        res = match_company(seg, companies)
        if res: return res
    res = match_company(filename, companies)
    if res: return res
    return "unknown"

def match_doctype(text: str, doc_types: list) -> dict:
    best_dt = None
    best_lvl = 99
    for dt in doc_types:
        for kw in dt.get("keywords", []):
            if kw.lower() in text.lower():
                lvl = get_level(dt.get("credibility", "L5"))
                if lvl < best_lvl:
                    best_lvl = lvl
                    best_dt = dt
    return best_dt

def get_doctype(segments: list, filename: str, doc_types: list, default_dt_id: str) -> dict:
    best_dt = None
    best_lvl = 99
    if "纪要合集" in segments:
        dt = next((d for d in doc_types if d["id"] == "meeting_minutes"), None)
        if dt:
            best_dt = dt
            best_lvl = get_level(dt.get("credibility", "L5"))
        if "业绩会" in segments:
            dt = next((d for d in doc_types if d["id"] == "earnings_calls"), None)
            if dt:
                best_dt = dt
                best_lvl = get_level(dt.get("credibility", "L5"))
        return best_dt

    for seg in reversed(segments):
        if "招股书&年报&业绩公告" in seg:
            if "招股" in filename: return next(d for d in doc_types if d["id"] == "prospectus")
            if "年报" in filename: return next(d for d in doc_types if d["id"] == "annual")
            if any(k in filename for k in ["季报", "中报", "半年报"]): return next(d for d in doc_types if d["id"] == "quarterly")
            return next(d for d in doc_types if d["id"] == "announcements")

        dt = match_doctype(seg, doc_types)
        if dt:
            lvl = get_level(dt.get("credibility", "L5"))
            if lvl < best_lvl:
                best_lvl = lvl
                best_dt = dt

    if best_dt: return best_dt
    dt = match_doctype(filename, doc_types)
    if dt: return dt
    return next((d for d in doc_types if d["id"] == default_dt_id), doc_types[0])

import argparse

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stage 4: Classify and Archive — 合规归档")
    p.add_argument("--workspace", required=True, help="Agent workspace 绝对路径")
    p.add_argument("--batch-id", required=True, help="批次 ID")
    return p.parse_args()

def resolve_shared_data_root(workspace: Path):
    # 1. 优先使用环境变量
    env_path = os.environ.get("OPENCLAW_DATA_DIR")
    if env_path and os.path.isdir(env_path):
        return Path(env_path)
    
    # 2. 线上生产环境标准路径探测
    production_candidate = Path("/root/.openclaw/workspace/data")
    if production_candidate.is_dir():
        return production_candidate
        
    # 3. 本地开发环境回退 (根据 workspace 推导)
    local_candidate = workspace / "workspace_data"
    if local_candidate.is_dir():
        return local_candidate
        
    return production_candidate # 默认返回生产路径

def main():
    args = parse_args()
    batch_id = args.batch_id
    workspace = Path(args.workspace).expanduser().resolve()
    manifest_path = workspace / "lark_sync" / "staging" / f"{batch_id}_manifest.jsonl"
    
    # 动态解析数据根目录
    data_root = resolve_shared_data_root(workspace)
    print(f"Using DATA_ROOT: {data_root}", file=sys.stderr)
    
    comp_path = data_root / "references" / "companies.json"
    dt_path = data_root / "references" / "doc_types.json"
    
    if not comp_path.exists():
        raise SystemExit(f"Error: companies.json not found at {comp_path}")
    
    companies = json.loads(comp_path.read_text())["companies"]
    dt_data = json.loads(dt_path.read_text())
    doc_types = dt_data["doc_types"]
    default_dt = dt_data.get("default_doc_type", "announcements")
    
    rows = []
    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip(): 
                row = json.loads(line)
                # Reset archived to parsed for re-run
                if row.get("stage") == "archived":
                    row["stage"] = "parsed"
                rows.append(row)
            
    stats = {"archived": 0, "unknown_company": 0, "failed": 0}
    archived_rows = []
    now = datetime.now(timezone.utc).isoformat()
    
    for row in rows:
        stage = row.get("stage", "")
        if stage not in ["parsed", "failed_parse"]:
            continue
            
        try:
            segments = row.get("feishu_path_segments", [])
            filename = row.get("file", "")
            
            # 1. Identity Company
            if "纪要合集" in segments:
                idx = segments.index("纪要合集")
                if idx + 1 < len(segments):
                    cid = match_company(segments[idx+1], companies) or "unknown"
                else: cid = "unknown"
            else:
                cid = get_company(segments, filename, companies)
            
            if cid == "unknown": stats["unknown_company"] += 1
            
            # 2. Identify Doctype & Credibility
            dt = get_doctype(segments, filename, doc_types, default_dt)
            credibility = dt.get("credibility", "L5")
            
            # 3. Target Dir construction (STRICT COMPLIANCE)
            if cid == "unknown":
                base_dir = data_root / "industry" / "unclassified" / "lark"
            else:
                base_dir = data_root / "companies" / cid / dt["dir"]
            
            src_dir = base_dir / "source"
            src_dir.mkdir(parents=True, exist_ok=True)
            
            # 4. Copy Source
            dl_path = row.get("abs_download_path", "")
            target_source_path = ""
            if dl_path and os.path.exists(dl_path):
                dest = src_dir / filename
                shutil.copy2(dl_path, str(dest))
                target_source_path = str(dest)
            
            # 5. Copy Parsed (Markdown)
            parsed_path = row.get("abs_parsed_path", "")
            target_parsed_path = ""
            if stage == "parsed" and parsed_path and os.path.exists(parsed_path):
                md_name = Path(parsed_path).name
                dest_md = base_dir / md_name
                shutil.copy2(parsed_path, str(dest_md))
                target_parsed_path = str(dest_md)
            
            # 6. Update Metadata in row
            row["company"] = cid
            row["doc_type"] = dt["id"]
            row["credibility"] = credibility
            row["target_source_path"] = str(Path(target_source_path).relative_to(data_root)) if target_source_path else ""
            row["target_parsed_path"] = str(Path(target_parsed_path).relative_to(data_root)) if target_parsed_path else ""
            row["abs_target_source_path"] = target_source_path
            row["abs_target_parsed_path"] = target_parsed_path
            row["stage"] = "archived"
            row["archived_at"] = now
            
            # 7. Build feishu source URL for traceability
            feishu_url = build_feishu_url(
                row.get("doc_token", ""),
                row.get("source_type", "drive"),
                row.get("file_type", ""),
            )
            row["feishu_url"] = feishu_url

            # 8. Update intake_log.jsonl
            if cid != "unknown":
                log_path = data_root / "companies" / cid / "intake_log.jsonl"
                log_entry = {
                    "item_id": f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{cid}-{dt['id']}",
                    "ts": now,
                    "company": cid,
                    "title": row.get("original_name"),
                    "doc_type": dt["id"],
                    "credibility": credibility,
                    "stored_rel_path": row["target_source_path"],
                    "feishu_url": feishu_url
                }
                with log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            # 9. Update timeline.md (STRICT COMPLIANCE)
            if cid != "unknown":
                timeline_path = data_root / "companies" / cid / "timeline.md"
                if not timeline_path.exists():
                    timeline_path.write_text(f"# {cid.upper()} Business Timeline\n\n", encoding="utf-8")

                feishu_ref = f"  - feishu: {feishu_url}\n" if feishu_url else ""
                with timeline_path.open("a", encoding="utf-8") as f:
                    line = (
                        f"- [{datetime.now().strftime('%Y-%m-%d')}] doc-routed\n"
                        f"  - type: {dt['id']} ({credibility})\n"
                        f"  - title: {row.get('original_name')}\n"
                        f"  - path: {row['target_source_path']}\n"
                        f"{feishu_ref}"
                    )
                    f.write(line)
            
            stats["archived"] += 1
            archived_rows.append(row)
            
        except Exception as e:
            row["stage"] = "failed_archive"
            row["error"] = str(e)
            stats["failed"] += 1

    # Final saves
    with manifest_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            
    state_path = workspace / "lark_sync" / "state" / "doc_states.jsonl"
    with state_path.open("a", encoding="utf-8") as f:
        for r in archived_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(json.dumps({
        "stage": "stage4_classify_archive_compliant",
        "ok": stats["failed"] == 0,
        "batch_id": batch_id,
        "archived": stats["archived"],
        "unknown_company": stats["unknown_company"],
        "failed": stats["failed"]
    }, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()