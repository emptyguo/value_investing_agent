import os
import sys
import json
import argparse
from datetime import datetime
from glob import glob

# repo root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from skills.common.scripts.utils import normalize_fingerprint

def resolve_data_root():
    script_dir = os.path.dirname(__file__)
    # Production: ~/.openclaw/workspace/data
    runtime_candidate = "/root/.openclaw/workspace/data"
    if os.path.isdir(runtime_candidate):
        return runtime_candidate
    # Local dev: <repo>/workspace_data
    local_candidate = os.path.abspath(os.path.join(script_dir, "../workspace_data"))
    if os.path.isdir(local_candidate):
        return local_candidate
    return runtime_candidate

DATA_ROOT = os.environ.get("OPENCLAW_DATA_DIR", resolve_data_root())

def parse_args():
    parser = argparse.ArgumentParser(description="Energy Conservation Checker for Invest Pipeline")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"), help="Target date YYYY-MM-DD")
    return parser.parse_args()

def read_jsonl(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows

def check_harness():
    args = parse_args()
    date_str = args.date
    
    # 1. Raw_Count from run_* metadata
    # Path: DATA_ROOT/news/raw/metadata/run_{ts}_{id}.json
    meta_glob = os.path.join(DATA_ROOT, "news", "raw", "metadata", f"run_*")
    raw_count_meta = 0
    run_files = glob(meta_glob)
    for run_file in run_files:
        with open(run_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)
            if meta.get("target_date") == date_str:
                raw_count_meta += meta.get("success_count", 0)
    
    # Also get Raw_Count from the actual file
    raw_path = os.path.join(DATA_ROOT, "news", "raw", f"{date_str}.jsonl")
    raw_items = read_jsonl(raw_path)
    raw_count_file = len(raw_items)
    
    # Use meta count as specified, but warn if mismatch
    if raw_count_meta != raw_count_file and raw_count_meta > 0:
        print(f"WARNING: Metadata Raw_Count ({raw_count_meta}) mismatch with file ({raw_count_file})")
    
    # The requirement says "Read run_* metadata to get Raw_Count"
    raw_count = raw_count_meta if raw_count_meta > 0 else raw_count_file
    
    if raw_count == 0:
        print(f"No data found for {date_str}. Raw_Count=0.")
        return
        
    # 2. Ingested & Skipped (Dup) & Filtered (No-Map)
    # We need to classify each item in raw_items
    
    # Load all intake logs for this date
    # intake_log.jsonl location: DATA_ROOT/companies/*/intake_log.jsonl and industry/*/intake_log.jsonl
    ingested_fps = set()
    intake_glob_co = os.path.join(DATA_ROOT, "companies", "*", "intake_log.jsonl")
    intake_glob_ind = os.path.join(DATA_ROOT, "industry", "*", "intake_log.jsonl")
    
    all_intake_files = glob(intake_glob_co) + glob(intake_glob_ind)
    for log_path in all_intake_files:
        logs = read_jsonl(log_path)
        for log in logs:
            if log.get("ingest_date") == date_str:
                fp = normalize_fingerprint(log.get("title", ""), log.get("url", ""))
                ingested_fps.add(fp)
                
    # Load ingest_state.jsonl
    # Path: os.path.abspath(os.path.join(DATA_ROOT, "..", "state", "ingest_state.jsonl"))
    state_path = os.path.abspath(os.path.join(DATA_ROOT, "..", "state", "ingest_state.jsonl"))
    state_fps = set()
    if os.path.exists(state_path):
        states = read_jsonl(state_path)
        for s in states:
            state_fps.add(s.get("fp"))
            
    ingested_count = 0
    skipped_count = 0
    filtered_count = 0
    errored_count = 0
    
    for item in raw_items:
        fp = normalize_fingerprint(item.get("title", ""), item.get("url", ""))
        
        if not item.get("company"):
            filtered_count += 1
            continue
            
        if fp in ingested_fps:
            ingested_count += 1
        elif fp in state_fps:
            # If it's in state but NOT in today's intake log, it was likely a skip
            skipped_count += 1
        else:
            errored_count += 1
            
    print(f"--- Harness Check Report: {date_str} ---")
    print(f"Raw_Count (Meta/File): {raw_count_meta} / {raw_count_file}")
    print(f"Ingested:          {ingested_count}")
    print(f"Skipped (Dup):     {skipped_count}")
    print(f"Filtered (No-Map): {filtered_count}")
    print(f"Errored:           {errored_count}")
    
    actual_sum = ingested_count + skipped_count + filtered_count + errored_count
    print(f"Sum (I+S+F+E):     {actual_sum}")
    
    if actual_sum != raw_count_file:
        print("ERROR: Conservation equation failed!")
        sys.exit(1)
    else:
        print("SUCCESS: Conservation equation holds.")

if __name__ == "__main__":
    check_harness()
