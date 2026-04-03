import json
import pytest
import os
import importlib.util
import sys

# Import the module dynamically since the path contains a hyphen
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
module_path = os.path.join(repo_root, "skills/invest-digest/scripts/generate_digest.py")
spec = importlib.util.spec_from_file_location("generate_digest", module_path)
generate_digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generate_digest)
write_digest_json = generate_digest.write_digest_json

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
