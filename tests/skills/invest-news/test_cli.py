import pytest
import importlib.util
import sys
import os

# Import the module dynamically since the path contains a hyphen
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../"))
module_path = os.path.join(repo_root, "skills/invest-news/scripts/fetch_news.py")
spec = importlib.util.spec_from_file_location("fetch_news", module_path)
fetch_news = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch_news)
parse_args = fetch_news.parse_args

def test_cli_mutex_group():
    # Should fail if both --all and --subject are provided
    with pytest.raises(SystemExit):
        parse_args(["--all", "--subject", "tme"])

def test_cli_defaults():
    args = parse_args(["--all"])
    assert args.all is True
    assert args.mode == "all"
    assert args.date is not None # Should default to today in Asia/Shanghai
