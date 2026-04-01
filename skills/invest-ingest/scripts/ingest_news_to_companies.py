import argparse
import json
import os
from datetime import datetime


def resolve_data_root():
    script_dir = os.path.dirname(__file__)
    # Production: ~/.openclaw/workspace/data
    runtime_candidate = os.path.abspath(os.path.join(script_dir, "../../../../data"))
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


def append_timeline(company_id, ingest_date, raw_saved, notes_saved):
    timeline_path = os.path.join(DATA_ROOT, "companies", company_id, "timeline.md")
    os.makedirs(os.path.dirname(timeline_path), exist_ok=True)
    if not os.path.exists(timeline_path):
        with open(timeline_path, "w", encoding="utf-8") as f:
            f.write(f"# {company_id.capitalize()} Timeline\n\n")

    entry = (
        f"- [{ingest_date}] news-ingest\n"
        f"  - raw +{raw_saved}, notes +{notes_saved}\n"
    )
    with open(timeline_path, "a", encoding="utf-8") as f:
        f.write(entry)


def main():
    args = parse_args()
    news_raw_path = os.path.join(DATA_ROOT, "news", "raw", f"{args.date}.jsonl")
    items = read_jsonl(news_raw_path)
    if not items:
        print(f"No source rows found: {news_raw_path}")
        return 0

    grouped = {}
    for item in items:
        company_id = item.get("company")
        if not company_id:
            continue
        grouped.setdefault(company_id, []).append(item)

    if not grouped:
        print(f"No company-tagged rows found in: {news_raw_path}")
        return 0

    total_raw_saved = 0
    total_notes_saved = 0
    for company_id, rows in grouped.items():
        company_root = os.path.join(DATA_ROOT, "companies", company_id)
        # Write to news/ subdirectory, not root
        raw_target = os.path.join(company_root, "news", "raw", f"{args.date}.jsonl")
        notes_target = os.path.join(company_root, "news", "notes", f"{args.date}.jsonl")

        fp_keys = ["ts", "source", "title", "url", "company"]
        raw_saved = append_jsonl_dedup(raw_target, rows, fingerprint_keys=fp_keys)
        notes_saved = append_jsonl_dedup(
            notes_target, [to_note(x) for x in rows], fingerprint_keys=fp_keys
        )
        append_timeline(company_id, args.date, raw_saved, notes_saved)
        total_raw_saved += raw_saved
        total_notes_saved += notes_saved
        print(f"[{company_id}] raw_saved={raw_saved} notes_saved={notes_saved}")

    print(
        f"Ingest completed for {args.date}: companies={len(grouped)} "
        f"total_raw_saved={total_raw_saved} total_notes_saved={total_notes_saved}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
