import json
import argparse
from pathlib import Path
from collections import Counter

def parse_args():
    p = argparse.ArgumentParser(description="Generate full lifecycle summary for a batch.")
    p.add_argument("--workspace", required=True)
    p.add_argument("--batch-id", required=True)
    p.add_argument("--silent-if-empty", action="store_true", help="Don't output anything if no files were archived.")
    return p.parse_args()

def main():
    args = parse_args()
    workspace = Path(args.workspace).expanduser().resolve()
    manifest_path = workspace / "lark_sync" / "staging" / f"{args.batch_id}_manifest.jsonl"
    
    if not manifest_path.exists():
        if not args.silent_if_empty:
            print(f"Error: Manifest not found at {manifest_path}")
        return

    rows = []
    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    total = len(rows)
    
    # Counter logic
    stages = Counter()
    companies = Counter()
    doc_types = Counter()
    errors = []

    for row in rows:
        stage = row.get("stage", "unknown")
        stages[stage] += 1
        
        if stage == "archived":
            companies[row.get("company", "unknown")] += 1
            doc_types[row.get("doc_type", "unknown")] += 1
            
        if "failed" in stage:
            errors.append({
                "file": row.get("original_name") or row.get("file"),
                "stage": stage,
                "error": row.get("error", "Unknown error")[:100] + "..."
            })

    # 静默判断逻辑
    if args.silent_if_empty and stages['archived'] == 0 and len(errors) == 0:
        return

    # Terminal output (Human readable)
    print("\n" + "="*60)
    print(f" 📊 INVEST LARK SYNC BATCH SUMMARY: {args.batch_id}")
    print("="*60)
    
    print(f"\n1. Lifecycle Stats:")
    print(f"   - Total Discovered: {total}")
    print(f"   - Archived (Done):  {stages['archived']}")
    print(f"   - Downloaded:       {stages['downloaded']}")
    print(f"   - Parsed:           {stages['parsed']}")
    print(f"   - Skipped:          {stages['skipped_unchanged']}")
    print(f"   - Failed:           {sum(v for k,v in stages.items() if 'failed' in k)}")

    if companies:
        print(f"\n2. Archive Distribution (By Company):")
        for c, count in companies.items():
            print(f"   - {c}: {count} files")

    if doc_types:
        print(f"\n3. Document Type Stats:")
        for dt, count in doc_types.items():
            print(f"   - {dt}: {count}")

    if errors:
        print(f"\n4. Failed Items (Top 5):")
        for err in errors[:5]:
            print(f"   - [{err['stage']}] {err['file']}: {err['error']}")
        if len(errors) > 5:
            print(f"     ... and {len(errors)-5} more errors.")

    print("\n" + "="*60)
    print(f" Report generated at: {Path().cwd()}")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()