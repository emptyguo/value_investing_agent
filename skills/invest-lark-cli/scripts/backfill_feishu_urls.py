"""
一次性回填脚本：从已有 manifest 中提取 feishu_url，补写到 timeline.md 和 intake_log.jsonl。

用法：
  python3 skills/invest-lark-cli/scripts/backfill_feishu_urls.py \
    --workspace /root/.openclaw/workspace/agents/mifeng_corporate_hub

工作原理：
  1. 扫描 {workspace}/lark_sync/staging/*_manifest.jsonl 中所有 stage=archived 的记录
  2. 用 doc_token + source_type + file_type 构造 feishu_url
  3. 补写到对应公司的 timeline.md（追加 feishu 行）和 intake_log.jsonl（补 feishu_url 字段）
  4. 幂等：已有 feishu_url 的 intake_log 记录不重复写入
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from skills.common.scripts.utils import build_feishu_url


def resolve_data_root(workspace: Path):
    env_path = os.environ.get("OPENCLAW_DATA_DIR")
    if env_path and os.path.isdir(env_path):
        return Path(env_path)
    production = Path("/root/.openclaw/workspace/data")
    if production.is_dir():
        return production
    local = workspace / "workspace_data"
    if local.is_dir():
        return local
    return production


def load_existing_urls(log_path: Path) -> set:
    """读取 intake_log.jsonl，返回已有 feishu_url 对应的 stored_rel_path 集合"""
    seen = set()
    if not log_path.exists():
        return seen
    for line in log_path.read_text(encoding="utf-8").strip().splitlines():
        try:
            entry = json.loads(line)
            if entry.get("feishu_url"):
                seen.add(entry.get("stored_rel_path", ""))
        except json.JSONDecodeError:
            continue
    return seen


def main():
    parser = argparse.ArgumentParser(description="Backfill feishu URLs from manifests")
    parser.add_argument("--workspace", required=True, help="Agent workspace 绝对路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印，不写入")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    data_root = resolve_data_root(workspace)
    staging_dir = workspace / "lark_sync" / "staging"

    if not staging_dir.exists():
        print(f"staging 目录不存在: {staging_dir}", file=sys.stderr)
        sys.exit(1)

    # 收集所有 manifest 中的 archived 记录
    manifests = sorted(staging_dir.glob("*_manifest.jsonl"))
    print(f"找到 {len(manifests)} 个 manifest 文件", file=sys.stderr)

    # 按公司聚合
    by_company = {}  # company_id -> [records]
    total = 0
    skipped = 0

    for mf in manifests:
        for line in mf.read_text(encoding="utf-8").strip().splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            if row.get("stage") != "archived":
                continue

            company = row.get("company", "unknown")
            if company == "unknown":
                continue

            doc_token = row.get("doc_token", "")
            if not doc_token:
                skipped += 1
                continue

            feishu_url = build_feishu_url(
                doc_token,
                row.get("source_type", "drive"),
                row.get("file_type", "")
            )

            by_company.setdefault(company, []).append({
                "title": row.get("original_name", row.get("file", "")),
                "doc_type": row.get("doc_type", ""),
                "credibility": row.get("credibility", ""),
                "stored_rel_path": row.get("target_source_path", ""),
                "feishu_url": feishu_url,
                "archived_at": row.get("archived_at", ""),
            })
            total += 1

    print(f"共 {total} 条归档记录需回填，{skipped} 条无 doc_token 跳过", file=sys.stderr)

    # 按公司写入
    timeline_count = 0
    log_count = 0

    for cid, records in sorted(by_company.items()):
        company_dir = data_root / "companies" / cid
        timeline_path = company_dir / "timeline.md"
        log_path = company_dir / "intake_log.jsonl"

        # 读取已有 intake_log 中有 feishu_url 的记录
        existing = load_existing_urls(log_path)

        timeline_lines = []
        log_entries = []

        for rec in records:
            rel_path = rec["stored_rel_path"]

            # 幂等：已有 feishu_url 的跳过
            if rel_path in existing:
                continue

            # timeline 追加
            timeline_lines.append(
                f"- [backfill] feishu link for: {rec['title']}\n"
                f"  - type: {rec['doc_type']} ({rec['credibility']})\n"
                f"  - path: {rel_path}\n"
                f"  - feishu: {rec['feishu_url']}\n"
            )
            timeline_count += 1

            # intake_log 追加（补充条目）
            log_entries.append({
                "item_id": f"backfill-{cid}-{Path(rel_path).stem}",
                "ts": rec["archived_at"] or datetime.now().isoformat(),
                "company": cid,
                "title": rec["title"],
                "doc_type": rec["doc_type"],
                "credibility": rec["credibility"],
                "stored_rel_path": rel_path,
                "feishu_url": rec["feishu_url"],
                "backfilled": True,
            })
            log_count += 1

        if args.dry_run:
            if timeline_lines:
                print(f"\n=== {cid} timeline.md 追加 {len(timeline_lines)} 条 ===")
                for tl in timeline_lines:
                    print(tl)
            if log_entries:
                print(f"=== {cid} intake_log.jsonl 追加 {len(log_entries)} 条 ===")
                for le in log_entries:
                    print(json.dumps(le, ensure_ascii=False))
        else:
            if timeline_lines:
                company_dir.mkdir(parents=True, exist_ok=True)
                with timeline_path.open("a", encoding="utf-8") as f:
                    f.write(f"\n## Feishu URL Backfill ({datetime.now().strftime('%Y-%m-%d')})\n\n")
                    for tl in timeline_lines:
                        f.write(tl)

            if log_entries:
                with log_path.open("a", encoding="utf-8") as f:
                    for le in log_entries:
                        f.write(json.dumps(le, ensure_ascii=False) + "\n")

    print(f"\n完成: timeline +{timeline_count} 条, intake_log +{log_count} 条", file=sys.stderr)
    if args.dry_run:
        print("(dry-run 模式，未实际写入)", file=sys.stderr)


if __name__ == "__main__":
    main()
