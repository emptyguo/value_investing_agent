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
