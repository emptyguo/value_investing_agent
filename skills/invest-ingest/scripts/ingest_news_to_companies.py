import argparse
import json
import os
from datetime import datetime


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


def append_jsonl_dedup(path, rows, fingerprint_keys):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    seen = set()
    if os.path.exists(path):
        for item in read_jsonl(path):
            seen.add(make_fingerprint(item, fingerprint_keys))

    saved = 0
    with open(path, "a", encoding="utf-8") as f:
        for row in rows:
            fp = make_fingerprint(row, fingerprint_keys)
            if fp in seen:
                continue
            seen.add(fp)
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            saved += 1
    return saved


def make_fingerprint(item, keys):
    return "||".join(str(item.get(k, "")).strip() for k in keys)


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
    timeline_path = os.path.join(DATA_ROOT, root_subdir, entity_id, "timeline.md")
    os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
    if not os.path.exists(timeline_path):
        with open(timeline_path, "w", encoding="utf-8") as f:
            f.write(f"# {entity_id.capitalize()} Timeline\n\n")

    entry = (
        f"- [{ingest_date}] news-ingest\n"
        f"  - raw +{raw_saved}, notes +{notes_saved}\n"
    )
    with open(timeline_path, "a", encoding="utf-8") as f:
        f.write(entry)


def append_intake_log(root_subdir, entity_id, rows, ingest_date):
    log_path = os.path.join(DATA_ROOT, root_subdir, entity_id, "intake_log.jsonl")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
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
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


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

    # Load mapping
    co_to_ind = load_company_industry_map()

    grouped_co = {}
    grouped_ind = {}
    
    for item in items:
        company_id = item.get("company")
        if not company_id:
            continue
        
        # Route to company
        grouped_co.setdefault(company_id, []).append(item)
        
        # Route to industry if applicable
        if item.get("match_type") == "industry":
            industry_id = co_to_ind.get(company_id)
            if industry_id:
                grouped_ind.setdefault(industry_id, []).append(item)

    total_raw_saved = 0
    
    # Process Companies
    for company_id, rows in grouped_co.items():
        target_dir = os.path.join(DATA_ROOT, "companies", company_id)
        raw_target = os.path.join(target_dir, "news", "raw", f"{args.date}.jsonl")
        notes_target = os.path.join(target_dir, "news", "notes", f"{args.date}.jsonl")

        fp_keys = ["ts", "source", "title", "url", "company"]
        raw_saved = append_jsonl_dedup(raw_target, rows, fingerprint_keys=fp_keys)
        notes_saved = append_jsonl_dedup(
            notes_target, [to_note(x) for x in rows], fingerprint_keys=fp_keys
        )
        append_timeline("companies", company_id, args.date, raw_saved, notes_saved)
        if raw_saved > 0:
            append_intake_log("companies", company_id, rows, args.date)
        total_raw_saved += raw_saved
        print(f"[Company: {company_id}] raw_saved={raw_saved}")

    # Process Industries
    for industry_id, rows in grouped_ind.items():
        target_dir = os.path.join(DATA_ROOT, "industry", industry_id)
        raw_target = os.path.join(target_dir, "news", "raw", f"{args.date}.jsonl")
        notes_target = os.path.join(target_dir, "news", "notes", f"{args.date}.jsonl")

        fp_keys = ["ts", "source", "title", "url"] # Less strict for industry dedup
        raw_saved = append_jsonl_dedup(raw_target, rows, fingerprint_keys=fp_keys)
        notes_saved = append_jsonl_dedup(
            notes_target, [to_note(x) for x in rows], fingerprint_keys=fp_keys
        )
        append_timeline("industry", industry_id, args.date, raw_saved, notes_saved)
        if raw_saved > 0:
            append_intake_log("industry", industry_id, rows, args.date)
        print(f"[Industry: {industry_id}] raw_saved={raw_saved}")

    print(f"Ingest completed for {args.date}: total_raw_saved={total_raw_saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
