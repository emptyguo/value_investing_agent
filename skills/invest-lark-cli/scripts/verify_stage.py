#!/usr/bin/env python3
import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Set


STAGE_ALIASES = {
    "stage1": "stage1_inventory",
    "stage1_inventory": "stage1_inventory",
    "stage2": "stage2_download",
    "stage2_download": "stage2_download",
    "stage3": "stage3_parse",
    "stage3_parse": "stage3_parse",
    "stage4": "stage4_classify_archive",
    "stage4_classify_archive": "stage4_classify_archive",
}


EXPECTED_STAGES: Dict[str, Set[str]] = {
    "stage1_inventory": {"inventoried", "skipped_unchanged", "failed_inventory"},
    "stage2_download": {"downloaded", "skipped_unchanged", "failed_download"},
    "stage3_parse": {"parsed", "skipped_unchanged", "failed_parse", "failed_download"},
    "stage4_classify_archive": {
        "classified",
        "archived",
        "skipped_unchanged",
        "failed_classify",
        "failed_archive",
        "failed_download",
    },
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Verify invest-lark-cli stage outputs.")
    p.add_argument("--workspace", required=True, help="Agent workspace path.")
    p.add_argument("--batch-id", required=True, help="Batch id, e.g. 20260401-154600.")
    p.add_argument(
        "--stage",
        required=True,
        choices=sorted(STAGE_ALIASES.keys()),
        help="Stage to verify.",
    )
    p.add_argument("--manifest-path", help="Optional explicit manifest path.")
    return p.parse_args()


def resolve_manifest_path(workspace: Path, batch_id: str, manifest_path: str = "") -> Path:
    if manifest_path:
        return Path(manifest_path).expanduser().resolve()
    return (workspace / "lark_sync" / "staging" / f"{batch_id}_manifest.jsonl").resolve()


def load_manifest(path: Path) -> List[dict]:
    rows: List[dict] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def check_stage_values(rows: List[dict], expected: Set[str], errors: List[str]) -> Counter:
    counts = Counter()
    for i, row in enumerate(rows):
        stage = str(row.get("stage", "")).strip()
        counts[stage] += 1
        if stage not in expected:
            errors.append(f"row[{i}] stage='{stage}' not in expected={sorted(expected)}")
    return counts


def check_file_exists(rows: List[dict], stage_name: str, errors: List[str]) -> int:
    checked = 0
    for i, row in enumerate(rows):
        stage = row.get("stage", "")
        if stage_name == "stage2_download" and stage == "downloaded":
            path = row.get("abs_download_path", "")
            checked += 1
            if not path or not Path(path).exists():
                errors.append(f"row[{i}] missing abs_download_path file: {path}")
        elif stage_name == "stage3_parse" and stage == "parsed":
            path = row.get("abs_parsed_path", "")
            checked += 1
            if not path or not Path(path).exists():
                errors.append(f"row[{i}] missing abs_parsed_path file: {path}")
        elif stage_name == "stage4_classify_archive" and stage == "archived":
            src = row.get("abs_target_source_path", "")
            md = row.get("abs_target_parsed_path", "")
            if src:
                checked += 1
                if not Path(src).exists():
                    errors.append(f"row[{i}] missing archived source file: {src}")
            if md:
                checked += 1
                if not Path(md).exists():
                    errors.append(f"row[{i}] missing archived parsed file: {md}")
    return checked


def main() -> int:
    args = parse_args()
    stage_name = STAGE_ALIASES[args.stage]
    workspace = Path(args.workspace).expanduser().resolve()
    manifest_path = resolve_manifest_path(workspace, args.batch_id, args.manifest_path or "")
    rows = load_manifest(manifest_path)
    errors: List[str] = []

    if not manifest_path.exists():
        errors.append(f"manifest not found: {manifest_path}")
    if not rows:
        errors.append("manifest is empty")

    expected = EXPECTED_STAGES[stage_name]
    counts = check_stage_values(rows, expected, errors) if rows else Counter()
    checked_files = check_file_exists(rows, stage_name, errors) if rows else 0

    result = {
        "stage": stage_name,
        "batch_id": args.batch_id,
        "manifest_path": str(manifest_path),
        "total_records": len(rows),
        "stage_counts": dict(sorted(counts.items())),
        "checked_files": checked_files,
        "ok": len(errors) == 0,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
