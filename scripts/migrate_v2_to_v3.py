# Implement backup and rollback logic
import os
import shutil
import sys
import json
from datetime import datetime
from glob import glob

# repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from skills.common.scripts.utils import normalize_fingerprint, atomic_append_jsonl

def safe_migrate(data_dir):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"{data_dir}_backup_v2_{ts}"
    print(f"Creating backup at {backup_dir}...")
    try:
        shutil.copytree(data_dir, backup_dir)
        print(f"Backup complete at {backup_dir}. Proceeding with migration...")
    except Exception as e:
        print(f"Backup failed: {e}")
        sys.exit(1)

    # 1. Update all news/raw/*.jsonl
    raw_files = glob(os.path.join(data_dir, "news", "raw", "*.jsonl"))
    for fpath in raw_files:
        _update_jsonl_fingerprints(fpath)

    # 2. Update all companies/*/news/raw/*.jsonl and notes/*.jsonl
    co_raw_files = glob(os.path.join(data_dir, "companies", "*", "news", "raw", "*.jsonl"))
    co_notes_files = glob(os.path.join(data_dir, "companies", "*", "news", "notes", "*.jsonl"))
    for fpath in co_raw_files + co_notes_files:
        _update_jsonl_fingerprints(fpath)

    # 3. Update all industry/*/news/raw/*.jsonl and notes/*.jsonl
    ind_raw_files = glob(os.path.join(data_dir, "industry", "*", "news", "raw", "*.jsonl"))
    ind_notes_files = glob(os.path.join(data_dir, "industry", "*", "news", "notes", "*.jsonl"))
    for fpath in ind_raw_files + ind_notes_files:
        _update_jsonl_fingerprints(fpath)

    # 4. Rebuild ingest_state.jsonl from all intake_log.jsonl
    # Since we changed fp algorithm, old state is invalid.
    state_path = os.path.abspath(os.path.join(data_dir, "..", "state", "ingest_state.jsonl"))
    if os.path.exists(state_path):
        print(f"Rebuilding {state_path}...")
        _rebuild_ingest_state(data_dir, state_path)

    print("\nMigration finished. If errors occur, run: ")
    print(f"rm -rf {data_dir} && mv {backup_dir} {data_dir}")

def _update_jsonl_fingerprints(fpath):
    print(f"Updating fingerprints in {fpath}...")
    rows = []
    with open(fpath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    item = json.loads(line)
                    # Recalculate fingerprint
                    fp = normalize_fingerprint(item.get("title", ""), item.get("url", ""))
                    item["fingerprint"] = fp
                    rows.append(item)
                except json.JSONDecodeError:
                    pass
    
    # Overwrite
    with open(fpath, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

def _rebuild_ingest_state(data_dir, state_path):
    # Get all intake logs
    intake_glob_co = os.path.join(data_dir, "companies", "*", "intake_log.jsonl")
    intake_glob_ind = os.path.join(data_dir, "industry", "*", "intake_log.jsonl")
    all_intake_files = glob(intake_glob_co) + glob(intake_glob_ind)
    
    new_state_records = []
    seen_keys = set()
    
    for log_path in all_intake_files:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        log = json.loads(line)
                        entity = log.get("entity")
                        title = log.get("title")
                        url = log.get("url")
                        action = "news_route" # default action in ingest script
                        
                        if entity and title and url:
                            fp = normalize_fingerprint(title, url)
                            key = f"{entity}:{fp}:{action}"
                            if key not in seen_keys:
                                seen_keys.add(key)
                                new_state_records.append({"entity": entity, "fp": fp, "action": action})
                    except json.JSONDecodeError:
                        pass
    
    # Write new state
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, 'w', encoding='utf-8') as f:
        for record in new_state_records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Safe migration from v2 to v3 with fingerprint recalculation.")
    default_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "workspace_data"))
    parser.add_argument("--data_dir", default=os.environ.get("OPENCLAW_DATA_DIR", default_data_dir), help="Path to data directory")
    args = parser.parse_args()
    
    safe_migrate(args.data_dir)
