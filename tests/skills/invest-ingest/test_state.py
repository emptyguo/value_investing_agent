import os
import sys
import importlib.util
import pytest
import json

# Import the module dynamically since the path contains a hyphen
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
module_path = os.path.join(repo_root, "skills/invest-ingest/scripts/ingest_news_to_companies.py")
spec = importlib.util.spec_from_file_location("ingest_news_to_companies", module_path)
ingest_news_to_companies = importlib.util.module_from_spec(spec)
sys.modules["ingest_news_to_companies"] = ingest_news_to_companies
spec.loader.exec_module(ingest_news_to_companies)

_get_state_keys = ingest_news_to_companies._get_state_keys
# Use atomic_append_jsonl for marking as ingested in test
atomic_append_jsonl = ingest_news_to_companies.atomic_append_jsonl

def test_ingest_state_idempotency(tmp_path):
    state_file = tmp_path / "ingest_state.jsonl"
    entity_id = "tme"
    fp = "hash123"
    action = "news_route"
    
    state_key = f"{entity_id}:{fp}:{action}"
    
    # 1. Initial state empty
    assert state_key not in _get_state_keys(str(state_file))
    
    # 2. Mark as ingested
    record = {"entity": entity_id, "fp": fp, "action": action}
    atomic_append_jsonl(str(state_file), [record])
    
    # 3. Verify state updated
    assert state_key in _get_state_keys(str(state_file))
