import argparse
import fcntl
import json
import os
import sys
from datetime import datetime

# Inject utils path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))
from skills.common.scripts.utils import atomic_append_jsonl, normalize_fingerprint


def resolve_data_root():
    script_dir = os.path.dirname(__file__)
    # Production: ~/.openclaw/workspace/data
    runtime_candidate = "/root/.openclaw/workspace/data"
    if os.path.isdir(runtime_candidate):
        return runtime_candidate
    # Local dev: <repo>/workspace_data
    local_candidate = os.path.abspath(os.path.join(script_dir, "../../../workspace_data"))
    if os.path.isdir(local_candidate):
        return local_candidate
    return runtime_candidate


DATA_ROOT = os.environ.get("OPENCLAW_DATA_DIR", resolve_data_root())


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest news/raw into per-company news directories.")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date to ingest, format YYYY-MM-DD",
    )
    return parser.parse_args()


def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _get_state_keys(state_path: str) -> set:
    keys = set()
    if not os.path.exists(state_path):
        return keys
    with open(state_path, 'r', encoding='utf-8') as f:
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            for line in f:
                if line.strip():
                    try:
                        data = json.loads(line)
                        keys.add(f"{data.get('entity')}:{data.get('fp')}:{data.get('action')}")
                    except json.JSONDecodeError:
                        pass
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return keys


def is_already_ingested(state_path: str, entity: str, fp: str, action: str) -> bool:
    keys = _get_state_keys(state_path)
    return f"{entity}:{fp}:{action}" in keys


def mark_as_ingested(state_path: str, entity: str, fp: str, action: str):
    record = {"entity": entity, "fp": fp, "action": action}
    atomic_append_jsonl(state_path, [record])


def to_note(item):
    return {
        "date": item.get("ts", "")[:10],
        "ts": item.get("ts", ""),
        "source": item.get("source", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "company": item.get("company", ""),
        "company_name": item.get("company_name", ""),
        "company_symbol": item.get("company_symbol", ""),
        "topic": item.get("raw_type", "news"),
        "confidence": "unrated",
        "verified_status": "unverified",
        "impact": "pending",
    }


def append_timeline(root_subdir, entity_id, ingest_date, raw_saved, notes_saved):
    """root_subdir: 'companies' or 'industry'"""
    if raw_saved == 0 and notes_saved == 0:
        return
        
    timeline_path = os.path.join(DATA_ROOT, root_subdir, entity_id, "timeline.md")
    os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
    
    entry = (
        f"- [{ingest_date}] news-ingest\n"
        f"  - raw +{raw_saved}, notes +{notes_saved}\n"
    )
    
    with open(timeline_path, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            if os.path.getsize(timeline_path) == 0:
                f.write(f"# {entity_id.capitalize()} Timeline\n\n")
            f.write(entry)
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def append_intake_log(root_subdir, entity_id, rows, ingest_date):
    log_path = os.path.join(DATA_ROOT, root_subdir, entity_id, "intake_log.jsonl")
    records = []
    for row in rows:
        log_entry = {
            "item_id": f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{entity_id}-news",
            "ts": datetime.now().isoformat(),
            "entity": entity_id,
            "input_type": "news_stream",
            "title": row.get("title"),
            "url": row.get("url"),
            "source": row.get("source"),
            "doc_type": "news",
            "credibility": "L6",
            "ingest_date": ingest_date
        }
        records.append(log_entry)
    atomic_append_jsonl(log_path, records)


def load_company_industry_map():
    path = os.path.join(DATA_ROOT, "references", "companies.json")
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {c["id"]: c.get("industry_id") for c in data.get("companies", []) if c.get("industry_id")}


def main():
    args = parse_args()
    news_raw_path = os.path.join(DATA_ROOT, "news", "raw", f"{args.date}.jsonl")
    items = read_jsonl(news_raw_path)
    if not items:
        print(f"No source rows found: {news_raw_path}")
        return 0

    co_to_ind = load_company_industry_map()
    grouped_co = {}
    grouped_ind = {}
    
    for item in items:
        company_id = item.get("company")
        if not company_id:
            continue
        
        grouped_co.setdefault(company_id, []).append(item)
        
        if item.get("match_type") == "industry":
            industry_id = co_to_ind.get(company_id)
            if industry_id:
                grouped_ind.setdefault(industry_id, []).append(item)

    total_raw_saved = 0
    state_path = os.path.abspath(os.path.join(DATA_ROOT, "..", "state", "ingest_state.jsonl"))
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    
    for company_id, rows in grouped_co.items():
        target_dir = os.path.join(DATA_ROOT, "companies", company_id)
        raw_target = os.path.join(target_dir, "news", "raw", f"{args.date}.jsonl")
        notes_target = os.path.join(target_dir, "news", "notes", f"{args.date}.jsonl")

        new_raws = []
        new_notes = []
        
        for row in rows:
            fp = normalize_fingerprint(row.get("title", ""), row.get("url", ""))
            if not is_already_ingested(state_path, company_id, fp, "news_route"):
                new_raws.append(row)
                new_notes.append(to_note(row))
                mark_as_ingested(state_path, company_id, fp, "news_route")

        raw_saved = len(new_raws)
        notes_saved = len(new_notes)

        if raw_saved > 0:
            atomic_append_jsonl(raw_target, new_raws)
            atomic_append_jsonl(notes_target, new_notes)
            append_timeline("companies", company_id, args.date, raw_saved, notes_saved)
            append_intake_log("companies", company_id, new_raws, args.date)

        total_raw_saved += raw_saved
        print(f"[Company: {company_id}] raw_saved={raw_saved}")

    for industry_id, rows in grouped_ind.items():
        target_dir = os.path.join(DATA_ROOT, "industry", industry_id)
        raw_target = os.path.join(target_dir, "news", "raw", f"{args.date}.jsonl")
        notes_target = os.path.join(target_dir, "news", "notes", f"{args.date}.jsonl")

        new_raws = []
        new_notes = []
        
        for row in rows:
            fp = normalize_fingerprint(row.get("title", ""), row.get("url", ""))
            if not is_already_ingested(state_path, industry_id, fp, "news_route"):
                new_raws.append(row)
                new_notes.append(to_note(row))
                mark_as_ingested(state_path, industry_id, fp, "news_route")

        raw_saved = len(new_raws)
        notes_saved = len(new_notes)

        if raw_saved > 0:
            atomic_append_jsonl(raw_target, new_raws)
            atomic_append_jsonl(notes_target, new_notes)
            append_timeline("industry", industry_id, args.date, raw_saved, notes_saved)
            append_intake_log("industry", industry_id, new_raws, args.date)
            
        print(f"[Industry: {industry_id}] raw_saved={raw_saved}")

    print(f"Ingest completed for {args.date}: total_raw_saved={total_raw_saved}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
