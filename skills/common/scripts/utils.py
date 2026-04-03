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
