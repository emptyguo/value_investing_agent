import os
import sys
import importlib.util
import pytest

# Import the module dynamically since the path contains a hyphen
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
module_path = os.path.join(repo_root, "skills/invest-ingest/scripts/ingest_news_to_companies.py")
spec = importlib.util.spec_from_file_location("ingest_news_to_companies", module_path)
ingest_news_to_companies = importlib.util.module_from_spec(spec)
sys.modules["ingest_news_to_companies"] = ingest_news_to_companies
spec.loader.exec_module(ingest_news_to_companies)

is_already_ingested = ingest_news_to_companies.is_already_ingested
mark_as_ingested = ingest_news_to_companies.mark_as_ingested

def test_ingest_state_idempotency(tmp_path):
    state_file = tmp_path / "ingest_state.jsonl"
    entity_id = "tme"
    fp = "hash123"
    action = "news_route"
    
    assert not is_already_ingested(str(state_file), entity_id, fp, action)
    mark_as_ingested(str(state_file), entity_id, fp, action)
    assert is_already_ingested(str(state_file), entity_id, fp, action)
