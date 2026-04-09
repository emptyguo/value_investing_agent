---
name: invest-lark-cli-v2
description: Minimal deterministic Feishu sync pipeline v2. Stage3 parse uses local CJS converter with OpenDataLoader PDF.
---

# Invest Lark CLI v2

Isolated v2 skill. Does not depend on `skills/invest-lark-cli`.

## Pipeline

State truth source:

- `{OPENCLAW_DATA_DIR}/lark_sync_v2/state/doc_states.jsonl`, keyed by `doc_token`
- Script namespace: `skills/invest-lark-cli-v2/scripts/sync/*.cjs`
- State file is guarded by an exclusive directory lock (`doc_states.jsonl.lock`); concurrent runs serialize safely.
- All four stages accept `--dry-run` for plan-only execution (no file writes, no state mutation).

### Stage1 Inventory

Generate temporary inventory and compare with the state source by `doc_token + feishu_updated_at`.

- missing state row: create `pending_download`
- same `feishu_updated_at`: keep existing state unchanged
- changed `feishu_updated_at`: reset to `pending_download`
- inventory 会调用 `drive/v1/metas/batch_query` 回填 `feishu_updated_at`/`feishu_created_at`（Unix 时间戳字符串）
- default source token: `LXzFfih46lPH67dmmOccMiKPn5b` (can still be overridden by `--source`)
- `--workspace` is optional (defaults to repository root)

```bash
node skills/invest-lark-cli-v2/scripts/sync/inventory.cjs
```

### Stage2 Download

Only process `pending_download` and `failed_download` (retry < max).

- success: `pending_parse` (retry_download reset to 0)
- fail: `failed_download` / `frozen_download`
- unsupported types (`sheet` / `bitable` / `slides` / `mindnote`) are frozen immediately with `last_error=unsupported_type:*`, no retries burned
- each `lark-cli` invocation has a 5-minute hard timeout (SIGKILL on expiry)

```bash
node skills/invest-lark-cli-v2/scripts/sync/download.cjs \
  --download-mode live
```

### Stage3 Parse (CJS)

Only process `pending_parse` and `failed_parse` (retry < max). Candidates are sorted small-file-first.

- markdown: copy -> `pending_archive` (`parse_method=copy`)
- pdf ≤ 50 MB: opendataloader-pdf CLI -> `pending_archive` (`parse_method=opendataloader`)
- pdf > 50 MB: **oversized skip** -> `pending_archive` (`parse_method=oversized_skip`, source file only at archive time)
- non pdf/markdown: `no_parse_required`
- fail: `failed_parse` / `frozen_parse`
- dynamic PDF timeout: `max(120s, 45s/MB)` bounded at 1500s, SIGKILL on expiry

```bash
node skills/invest-lark-cli-v2/scripts/sync/parse.cjs \
  --converter auto
```

### Stage4 Archive

Only process `pending_archive`, `no_parse_required`, and `failed_archive` (retry < max).

- classify by `feishu_path_segments` first, then filename
- unknown company routes to `industry/unclassified/lark`
- success: `archived`
- fail: `failed_archive` / `frozen_archive`

```bash
node skills/invest-lark-cli-v2/scripts/sync/archive.cjs
```

## Parse Options

Stage3 options:

- `--converter auto|opendataloader|cli|mock`
- `--state-file /abs/path/doc_states.jsonl`
- `--parsed-dir /abs/path/parsed`
- `--max-retries 3`

Notes:

- `auto` and `opendataloader` both run the CLI `opendataloader-pdf` (only path that supports a hard spawn timeout / SIGKILL). `mock` writes a stub markdown.
- OpenDataLoader PDF usually needs Java 11+ in `PATH`.
