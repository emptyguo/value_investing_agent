import json
import os
import argparse
import uuid
from pathlib import Path

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

def main():
    parser = argparse.ArgumentParser(description="Enforce v1.0 JSON schema contract for digests.")
    parser.add_argument("--path", required=True, help="Output JSON path")
    parser.add_argument("--date", required=True, help="Batch date YYYY-MM-DD")
    parser.add_argument("--ref-ids", nargs="+", required=True, help="List of news fingerprints")
    parser.add_argument("--total", type=int, required=True)
    parser.add_argument("--confidence", type=float, default=0.5)
    
    args = parser.parse_args()
    
    write_digest_json(
        path=args.path,
        digest_id=str(uuid.uuid4()),
        batch_date=args.date,
        ref_ids=args.ref_ids,
        total=args.total,
        referenced=len(args.ref_ids),
        confidence=args.confidence
    )
    print(f"Successfully wrote digest manifest to {args.path}")

if __name__ == "__main__":
    main()
