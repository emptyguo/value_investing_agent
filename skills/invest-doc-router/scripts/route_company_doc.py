import argparse
import json
import os
import shutil
from datetime import datetime


def resolve_shared_data_root():
    script_dir = os.path.dirname(__file__)
    runtime_candidate = os.path.abspath(os.path.join(script_dir, "../../../../data"))
    if os.path.isdir(runtime_candidate):
        return runtime_candidate
    local_candidate = os.path.abspath(os.path.join(script_dir, "../../../workspace_data"))
    if os.path.isdir(local_candidate):
        return local_candidate
    return runtime_candidate


SHARED_DATA_ROOT = os.environ.get("OPENCLAW_DATA_DIR", resolve_shared_data_root())


def find_config(filename):
    candidates = [
        os.path.join(SHARED_DATA_ROOT, "references", filename),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../workspace_data/references", filename)),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_valid_companies():
    path = find_config("companies.json")
    if not os.path.exists(path):
        return set()
    data = load_json(path)
    return {c["id"] for c in data.get("companies", [])}


def load_doc_types():
    path = find_config("doc_types.json")
    if not os.path.exists(path):
        raise SystemExit(f"doc_types.json not found: {path}")
    data = load_json(path)
    types = {}
    for entry in data.get("doc_types", []):
        types[entry["id"]] = entry
    default = data.get("default_doc_type", "announcements")
    return types, default


def parse_args():
    parser = argparse.ArgumentParser(description="Route company document to structured company library.")
    parser.add_argument("--company", required=True)
    parser.add_argument("--type", required=True, choices=["file", "link", "text"])
    parser.add_argument("--title", required=True)
    parser.add_argument("--doc-type", default="auto")
    parser.add_argument("--file-path")
    parser.add_argument("--url")
    parser.add_argument("--content", default="")
    parser.add_argument("--credibility-note", default="")
    return parser.parse_args()


def sanitize(name):
    safe = "".join(c if c.isalnum() or c in ("-", "_", ".") else "_" for c in name).strip("_")
    return safe or "item"


def now_ts():
    return datetime.now().isoformat(timespec="seconds")


def auto_classify(text, doc_types, default_type):
    s = (text or "").lower()
    for type_id, entry in doc_types.items():
        for kw in entry.get("keywords", []):
            if kw.lower() in s:
                return type_id, f"auto:{type_id}"
    return default_type, f"auto:{default_type}"


def ensure_company_paths(company, sub_dir):
    company_root = os.path.join(SHARED_DATA_ROOT, "companies", company)
    target_dir = os.path.join(company_root, sub_dir)
    os.makedirs(target_dir, exist_ok=True)
    timeline_path = os.path.join(company_root, "timeline.md")
    if not os.path.exists(timeline_path):
        with open(timeline_path, "w", encoding="utf-8") as f:
            f.write(f"# {company.capitalize()} Timeline\n\n")
    log_path = os.path.join(company_root, "intake_log.jsonl")
    return target_dir, timeline_path, log_path


def write_record_json(path, args, final_doc_type, credibility):
    payload = {
        "title": args.title,
        "input_type": args.type,
        "doc_type": final_doc_type,
        "credibility": credibility,
        "credibility_note": args.credibility_note,
        "url": args.url or "",
        "content": args.content or "",
        "created_at": now_ts(),
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=2))


def append_timeline(timeline_path, doc_type, credibility, title, stored_rel_path):
    line = (
        f"- [{datetime.now().strftime('%Y-%m-%d')}] doc-routed\n"
        f"  - type: {doc_type} ({credibility})\n"
        f"  - title: {title}\n"
        f"  - path: {stored_rel_path}\n"
    )
    with open(timeline_path, "a", encoding="utf-8") as f:
        f.write(line)


def append_log(log_path, payload):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main():
    args = parse_args()
    company = args.company.strip().lower()

    valid_companies = load_valid_companies()
    if valid_companies and company not in valid_companies:
        raise SystemExit(f"unsupported company: {company}. allowed={sorted(valid_companies)}")

    doc_types, default_type = load_doc_types()

    full_text = " ".join([args.title or "", args.url or "", args.file_path or "", args.content or ""])
    if args.doc_type == "auto":
        doc_type, rule = auto_classify(full_text, doc_types, default_type)
    else:
        doc_type = args.doc_type.strip()
        if doc_type not in doc_types:
            raise SystemExit(f"unsupported doc_type: {doc_type}. allowed={sorted(doc_types.keys())}")
        rule = "manual"

    entry = doc_types[doc_type]
    sub_dir = entry["dir"]
    credibility = entry["credibility"]

    target_dir, timeline_path, log_path = ensure_company_paths(company, sub_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    item_id = f"{stamp}-{company}-{doc_type}"

    if args.type == "file":
        if not args.file_path:
            raise SystemExit("--file-path is required for type=file")
        if not os.path.exists(args.file_path):
            raise SystemExit(f"file not found: {args.file_path}")
        base = sanitize(os.path.basename(args.file_path))
        stored_path = os.path.join(target_dir, f"{item_id}__{base}")
        shutil.copy2(args.file_path, stored_path)
    else:
        stored_path = os.path.join(target_dir, f"{item_id}.json")
        write_record_json(stored_path, args, doc_type, credibility)

    stored_rel_path = os.path.relpath(stored_path, SHARED_DATA_ROOT)
    append_timeline(timeline_path, doc_type, credibility, args.title, stored_rel_path)

    is_pdf = args.type == "file" and args.file_path and args.file_path.lower().endswith(".pdf")

    payload = {
        "item_id": item_id,
        "ts": now_ts(),
        "company": company,
        "input_type": args.type,
        "title": args.title,
        "url": args.url,
        "source_file": args.file_path,
        "doc_type": doc_type,
        "credibility": credibility,
        "credibility_note": args.credibility_note,
        "rule": rule,
        "stored_path": stored_path,
        "stored_rel_path": stored_rel_path,
        "needs_pdf_parse": is_pdf,
    }
    append_log(log_path, payload)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
