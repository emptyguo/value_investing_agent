import re
import hashlib
import json
import fcntl
import os
from typing import List, Dict, Any

def normalize_fingerprint(title: str, url: str) -> str:
    """
    Generate a SHA-256 fingerprint from a normalized title and URL.
    
    URL normalization: strips protocol, www., query parameters, fragments, trailing slashes, and converts to lowercase.
    Title normalization: strips all non-alphanumeric characters, whitespace, and converts to lowercase.
    """
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

def build_feishu_url(doc_token: str, source_type: str, file_type: str) -> str:
    """
    Construct a feishu source URL for traceability from a doc token.

    Returns "" if doc_token is empty. Routing rules:
      - source_type == "wiki"        -> /wiki/{token}
      - file_type in (doc, docx)     -> /docx/{token}
      - file_type == "sheet"         -> /sheets/{token}
      - file_type == "bitable"       -> /base/{token}
      - otherwise                    -> /file/{token}
    """
    if not doc_token:
        return ""
    if source_type == "wiki":
        return f"https://feishu.cn/wiki/{doc_token}"
    if file_type in ("doc", "docx"):
        return f"https://feishu.cn/docx/{doc_token}"
    if file_type == "sheet":
        return f"https://feishu.cn/sheets/{doc_token}"
    if file_type == "bitable":
        return f"https://feishu.cn/base/{doc_token}"
    return f"https://feishu.cn/file/{doc_token}"


def atomic_append_jsonl(filepath: str, rows: List[Dict[str, Any]]) -> None:
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
