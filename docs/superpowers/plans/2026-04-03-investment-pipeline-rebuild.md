# Investment Pipeline Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the invest-news, invest-ingest, and invest-digest skills to be idempotent, concurrent-safe, and fully traceable according to the v3 Harness-Grade spec.

**Architecture:** Implement strict URL/Title normalization for fingerprinting, fcntl-based atomic writes for state tracking (`ingest_state.jsonl`), CLI mutex groups for explicit contracts, and dual-output (Markdown + JSON) for digests. Introduce a local-first query routing rule for data fetching.

**Tech Stack:** Python 3, `argparse`, `hashlib`, `fcntl`, `json`, `datetime` (with `zoneinfo` or `pytz` for `Asia/Shanghai`), `shutil`.

---

### Task 1: Core Utilities (Normalization & Atomic Writes)

Create shared utilities to ensure all scripts use the exact same logic for ID generation and concurrent-safe file operations.

**Files:**
- Create: `skills/common/scripts/utils.py`
- Create: `tests/skills/common/test_utils.py`

- [ ] **Step 1: Write failing tests for normalization and atomic write**
```python
import os
import pytest
from skills.common.scripts.utils import normalize_fingerprint, atomic_append_jsonl

def test_normalize_fingerprint():
    # URL testing: strip http/https, www., query params, fragments, trailing slashes, lower case
    url1 = "https://www.example.com/path/?q=1#anchor"
    url2 = "http://example.com/path"
    
    # Title testing: strip whitespace, punctuation, lower case
    title1 = "  Hello, World!  "
    title2 = "helloworld"
    
    id1 = normalize_fingerprint(title1, url1)
    id2 = normalize_fingerprint(title2, url2)
    assert id1 == id2

def test_atomic_append_jsonl(tmp_path):
    test_file = tmp_path / "test.jsonl"
    data = {"key": "value"}
    atomic_append_jsonl(str(test_file), [data])
    assert test_file.exists()
    with open(test_file, 'r') as f:
        assert "value" in f.read()
```

- [ ] **Step 2: Run tests to verify they fail**
Run: `python -m pytest tests/skills/common/test_utils.py -v`
Expected: FAIL (ModuleNotFoundError or ImportError)

- [ ] **Step 3: Implement minimal code in `utils.py`**
```python
import re
import hashlib
import json
import fcntl
import os
import tempfile
import shutil

def normalize_fingerprint(title: str, url: str) -> str:
    # Normalize URL
    u = re.sub(r'^https?://', '', url)
    u = re.sub(r'^www\.', '', u)
    u = u.split('?')[0].split('#')[0]
    u = u.rstrip('/').lower()
    
    # Normalize Title
    t = re.sub(r'[^\w\s]', '', title)
    t = re.sub(r'\s+', '', t).lower()
    
    # Generate SHA-256
    raw = f"{t}{u}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()

def atomic_append_jsonl(filepath: str, rows: list):
    """Safely append rows to a JSONL file using fcntl locking."""
    if not rows:
        return
        
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, 'a', encoding='utf-8') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX)
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
            f.flush()
            os.fsync(f.fileno())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
```

- [ ] **Step 4: Run tests to verify they pass**
Run: `python -m pytest tests/skills/common/test_utils.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add skills/common/scripts/utils.py tests/skills/common/test_utils.py
git commit -m "feat(common): add strict fingerprinting and atomic jsonl append"
```

---

### Task 2: Refactor invest-news CLI and Fetching Logic

Update `fetch_news.py` to enforce mutually exclusive arguments, set correct defaults (Asia/Shanghai date), use the new fingerprint logic, and implement `metadata.json` logging per run.

**Files:**
- Modify: `skills/invest-news/scripts/fetch_news.py`

- [ ] **Step 1: Write failing test for CLI parsing**
Create `tests/skills/invest-news/test_cli.py`:
```python
import pytest
from skills.invest_news.scripts.fetch_news import parse_args

def test_cli_mutex_group():
    # Should fail if both --all and --subject are provided
    with pytest.raises(SystemExit):
        parse_args(["--all", "--subject", "tme"])

def test_cli_defaults():
    args = parse_args(["--all"])
    assert args.all is True
    assert args.mode == "all"
    assert args.date is not None # Should default to today in Asia/Shanghai
```

- [ ] **Step 2: Run test to verify failure**
Run: `python -m pytest tests/skills/invest-news/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement CLI changes and Run Metadata logic in `fetch_news.py`**
Modify `skills/invest-news/scripts/fetch_news.py`:
```python
import argparse
import sys
import json
import os
from datetime import datetime
import uuid
# Add zoneinfo for Python 3.9+ or pytz if older. Using datetime.timezone if simple offset is enough, but spec says Asia/Shanghai.
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo # Or require pytz

# ... existing imports and resolve_default_data_root ...
from skills.common.scripts.utils import normalize_fingerprint, atomic_append_jsonl

def parse_args(argv):
    parser = argparse.ArgumentParser(description="Fetch raw news based on v3 contract.")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Scan all companies")
    group.add_argument("--subject", help="Scan specific company ID")
    
    parser.add_argument("--mode", choices=["native", "akshare", "all"], default="all")
    
    # Default to Asia/Shanghai current date
    tz_sh = ZoneInfo("Asia/Shanghai")
    default_date = datetime.now(tz_sh).strftime("%Y-%m-%d")
    parser.add_argument("--date", default=default_date, help="Format YYYY-MM-DD")
    
    return parser.parse_args(argv)

def log_run_metadata(data_root, run_id, date_str, scope, mode, success_count):
    ts = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d_%H%M%S")
    meta_path = os.path.join(data_root, "news", "raw", "metadata", f"run_{ts}_{run_id}.json")
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    
    payload = {
        "run_id": run_id,
        "timestamp": ts,
        "target_date": date_str,
        "scope": scope,
        "mode": mode,
        "success_count": success_count
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

# Update save_to_raw to use atomic_append_jsonl and generate fingerprints
# Update main() to generate run_id = str(uuid.uuid4()), call log_run_metadata
```

- [ ] **Step 4: Run test to verify it passes**
Run: `python -m pytest tests/skills/invest-news/test_cli.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add skills/invest-news/scripts/fetch_news.py tests/skills/invest-news/test_cli.py
git commit -m "feat(invest-news): implement v3 CLI contract and run metadata logging"
```

---

### Task 3: invest-ingest Rebuild (Absolute Idempotency)

Replace timeline reading with an atomic `ingest_state.jsonl` check to prevent duplicate routing. Use `atomic_append_jsonl` for all writes.

**Files:**
- Modify: `skills/invest-ingest/scripts/ingest_news_to_companies.py`

- [ ] **Step 1: Write failing test for idempotent ingest state**
Create `tests/skills/invest-ingest/test_state.py`:
```python
import os
import json
from skills.invest_ingest.scripts.ingest_news_to_companies import is_already_ingested, mark_as_ingested

def test_ingest_state_idempotency(tmp_path):
    state_file = tmp_path / "ingest_state.jsonl"
    entity_id = "tme"
    fp = "hash123"
    action = "news_route"
    
    assert not is_already_ingested(str(state_file), entity_id, fp, action)
    mark_as_ingested(str(state_file), entity_id, fp, action)
    assert is_already_ingested(str(state_file), entity_id, fp, action)
```

- [ ] **Step 2: Run test to verify failure**
Run: `python -m pytest tests/skills/invest-ingest/test_state.py -v`
Expected: FAIL

- [ ] **Step 3: Implement state functions and integrate into main loop**
Modify `skills/invest-ingest/scripts/ingest_news_to_companies.py`:
```python
import fcntl
import json
import os
from skills.common.scripts.utils import atomic_append_jsonl

def _get_state_keys(state_path: str) -> set:
    keys = set()
    if not os.path.exists(state_path):
        return keys
    with open(state_path, 'r', encoding='utf-8') as f:
        # No lock needed for simple read if we accept slight eventual consistency on read, 
        # but to be safe we can lock.
        fcntl.flock(f, fcntl.LOCK_SH)
        try:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    keys.add(f"{data.get('entity')}:{data.get('fp')}:{data.get('action')}")
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return keys

def is_already_ingested(state_path: str, entity: str, fp: str, action: str) -> bool:
    keys = _get_state_keys(state_path)
    return f"{entity}:{fp}:{action}" in keys

def mark_as_ingested(state_path: str, entity: str, fp: str, action: str):
    record = {"entity": entity, "fp": fp, "action": action}
    atomic_append_jsonl(state_path, [record])

# In main():
# state_path = os.path.join(DATA_ROOT, "state", "ingest_state.jsonl")
# For each item, calculate fp = normalize_fingerprint(item['title'], item['url'])
# if not is_already_ingested(state_path, company_id, fp, "ingest"):
#    ... do ingest ...
#    mark_as_ingested(...)
```

- [ ] **Step 4: Run test to verify passes**
Run: `python -m pytest tests/skills/invest-ingest/test_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add skills/invest-ingest/scripts/ingest_news_to_companies.py tests/skills/invest-ingest/test_state.py
git commit -m "feat(invest-ingest): implement atomic ingest_state.jsonl for strict idempotency"
```

---

### Task 4: invest-digest Dual-State Contract

Create a Python script for `invest-digest` that enforces the JSON output schema when generating the markdown digest.

**Files:**
- Create: `skills/invest-digest/scripts/generate_digest.py`

- [ ] **Step 1: Write test for digest schema validation**
Create `tests/skills/invest-digest/test_schema.py`:
```python
import json
import pytest
from skills.invest_digest.scripts.generate_digest import write_digest_json

def test_digest_json_schema(tmp_path):
    out_file = tmp_path / "digest.json"
    write_digest_json(
        path=str(out_file),
        digest_id="uuid-123",
        batch_date="2026-04-03",
        ref_ids=["hash1"],
        total=10,
        referenced=8,
        confidence=0.9
    )
    
    data = json.loads(out_file.read_text())
    assert data["version"] == "1.0"
    assert data["digest_id"] == "uuid-123"
    assert "metrics" in data
    assert data["metrics"]["coverage"] == 0.8
```

- [ ] **Step 2: Run test to verify failure**
Run: `python -m pytest tests/skills/invest-digest/test_schema.py -v`
Expected: FAIL

- [ ] **Step 3: Implement `generate_digest.py`**
```python
import json
import os

def write_digest_json(path: str, digest_id: str, batch_date: str, ref_ids: list, total: int, referenced: int, confidence: float):
    coverage = referenced / total if total > 0 else 0.0
    payload = {
        "version": "1.0",
        "digest_id": digest_id,
        "batch_date": batch_date,
        "news_referenced_ids": ref_ids,
        "metrics": {
            "total_source_count": total,
            "referenced_count": referenced,
            "coverage": coverage,
            "confidence": confidence
        }
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

# Add CLI parsing for --company, --date, and mock LLM generation that calls write_digest_json
```

- [ ] **Step 4: Run test to verify passes**
Run: `python -m pytest tests/skills/invest-digest/test_schema.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add skills/invest-digest/scripts/generate_digest.py tests/skills/invest-digest/test_schema.py
git commit -m "feat(invest-digest): enforce v1.0 JSON schema contract alongside markdown output"
```

---

### Task 5: Harness Verification & Safe Migration

Implement the conservation equation checker and the safe migration script.

**Files:**
- Create: `scripts/harness_check.py`
- Create: `scripts/migrate_v2_to_v3.py`

- [ ] **Step 1: Write `harness_check.py`**
```python
# python3 scripts/harness_check.py --date 2026-04-03
# Implement logic:
# Raw_Count == Ingested + Skipped (Dup) + Filtered (No-Map) + Errored
# Read run_* metadata to get Raw_Count.
# Read intake_log.jsonl to get Ingested.
# Read ingest_state.jsonl to get Skipped.
# Print report and exit 1 if equation fails.
```

- [ ] **Step 2: Write `migrate_v2_to_v3.py`**
```python
# Implement backup and rollback logic
import os
import shutil
import sys
from datetime import datetime

def safe_migrate(data_dir):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = f"{data_dir}_backup_v2_{ts}"
    print(f"Creating backup at {backup_dir}...")
    shutil.copytree(data_dir, backup_dir)
    print("Backup complete. Proceeding with migration...")
    # Add logic to read old jsonl files, recalculate fp using new utils.py, and overwrite
    print("Migration finished. If errors occur, run: ")
    print(f"mv {data_dir} {data_dir}_failed && mv {backup_dir} {data_dir}")

if __name__ == "__main__":
    safe_migrate(os.environ.get("OPENCLAW_DATA_DIR", "/root/.openclaw/workspace/data"))
```

- [ ] **Step 3: Commit**
```bash
git add scripts/harness_check.py scripts/migrate_v2_to_v3.py
git commit -m "chore: add harness verification and v2 to v3 safe migration script"
```
