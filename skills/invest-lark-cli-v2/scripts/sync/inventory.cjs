#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const {
  acquireStateLock,
  appendEvent,
  ensureDir,
  loadStateMap,
  nextRunId,
  nowIso,
  readJsonl,
  releaseStateLock,
  resolvePaths,
  sanitizeFilename,
  saveStateMap,
  writeJsonlAtomic,
  writeRunLog,
} = require("../lib/common.cjs");

const DEFAULT_WORKSPACE = path.resolve(__dirname, "../../../../");
const DEFAULT_SOURCE_TOKEN = "LXzFfih46lPH67dmmOccMiKPn5b";

function printHelp() {
  console.log(
    [
      "Usage:",
      "  node skills/invest-lark-cli-v2/scripts/sync/inventory.cjs [options]",
      "",
      "Options:",
      `  --workspace /abs/workspace              # optional, default: ${DEFAULT_WORKSPACE}`,
      `  --source <folder-token-or-url>          # optional, default: ${DEFAULT_SOURCE_TOKEN}`,
      "  --inventory-file /abs/path/inventory.jsonl   # test/import mode (skip lark-cli traversal)",
      "  --state-file /abs/path/doc_states.jsonl",
    ].join("\n"),
  );
}

function parseArgs(argv) {
  const out = {
    workspace: DEFAULT_WORKSPACE,
    source: DEFAULT_SOURCE_TOKEN,
    inventoryFile: "",
    stateFile: "",
    dryRun: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--workspace") {
      out.workspace = String(argv[i + 1] || "").trim();
      i += 1;
    } else if (arg === "--source") {
      out.source = String(argv[i + 1] || "").trim();
      i += 1;
    } else if (arg === "--inventory-file") {
      out.inventoryFile = String(argv[i + 1] || "").trim();
      i += 1;
    } else if (arg === "--state-file") {
      out.stateFile = String(argv[i + 1] || "").trim();
      i += 1;
    } else if (arg === "--dry-run") {
      out.dryRun = true;
    } else if (arg === "-h" || arg === "--help") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return out;
}

function extractFolderToken(source) {
  const raw = String(source || "").trim();
  const match = /folder\/([A-Za-z0-9]+)/.exec(raw);
  if (match) {
    return match[1];
  }
  return raw;
}

function runLarkCli(args, timeout = 120000) {
  const cmd = ["lark-cli", ...args];
  if (!args.includes("--format")) {
    cmd.push("--format", "json");
  }
  const result = spawnSync(cmd[0], cmd.slice(1), {
    encoding: "utf-8",
    timeout,
  });
  if (result.error) {
    throw new Error(`lark-cli execution failed: ${result.error.message}`);
  }
  if (result.status !== 0) {
    throw new Error(`lark-cli exit=${result.status}: ${(result.stderr || "").trim()}`);
  }
  let payload;
  try {
    payload = JSON.parse(result.stdout || "{}");
  } catch (error) {
    throw new Error(`lark-cli returned non-json: ${error.message}`);
  }
  if (
    payload &&
    typeof payload === "object" &&
    Object.prototype.hasOwnProperty.call(payload, "code") &&
    Object.prototype.hasOwnProperty.call(payload, "data")
  ) {
    if (payload.code !== 0) {
      throw new Error(`lark api error code=${payload.code} msg=${payload.msg || ""}`);
    }
    return payload.data;
  }
  return payload;
}

function listDriveFolder(folderToken, pageToken = "", depth = 0) {
  let url = "";
  if (depth === 0) {
    url = `/open-apis/drive/v1/files?folder_token=${folderToken}&page_size=50`;
  } else {
    url = `/open-apis/drive/explorer/v2/folder/${folderToken}/children?page_size=50`;
  }
  if (pageToken) {
    url += `&page_token=${pageToken}`;
  }
  return runLarkCli(["api", "GET", url], 180000);
}

function walkDriveFolder(folderToken, parentPath = "", depth = 0, errors = []) {
  const files = [];
  let pageToken = "";
  while (true) {
    let data;
    try {
      data = listDriveFolder(folderToken, pageToken, depth);
    } catch (error) {
      // Record partial failure and stop walking this branch; do NOT abort
      // the whole inventory — sibling folders should still be scanned.
      errors.push({
        folder_token: folderToken,
        path: parentPath,
        depth,
        error: String(error && error.message ? error.message : error),
      });
      return files;
    }
    let items = [];
    if (depth === 0) {
      items = Array.isArray(data.files) ? data.files : [];
    } else if (data.children && typeof data.children === "object") {
      items = Object.values(data.children);
    } else {
      items = Array.isArray(data.files) ? data.files : [];
    }

    for (const item of items) {
      const itemType = String(item.type || "");
      const name = String(item.name || "");
      if (itemType === "folder") {
        const subToken = String(item.token || "");
        if (subToken) {
          const subPath = `${parentPath}${name}/`;
          files.push(...walkDriveFolder(subToken, subPath, depth + 1, errors));
        }
      } else {
        const pathSegments = parentPath.split("/").filter(Boolean);
        files.push({
          ...item,
          _feishu_path: parentPath,
          _feishu_path_segments: pathSegments,
          _depth: depth,
        });
      }
    }

    const hasMore =
      depth === 0
        ? Boolean(data.has_more)
        : Boolean(data.hasMore || data.has_more);
    pageToken = depth === 0 ? String(data.page_token || "") : String(data.nextPageToken || data.page_token || "");
    if (!hasMore) {
      break;
    }
  }
  return files;
}

const META_DOC_TYPES = new Set(["doc", "docx", "sheet", "bitable", "wiki", "mindnote", "slides", "file"]);

function metaDocType(rawType) {
  const dt = String(rawType || "").toLowerCase();
  if (META_DOC_TYPES.has(dt)) {
    return dt;
  }
  return "file";
}

function enrichItemsWithMetadata(items) {
  const candidates = [];
  for (const it of items) {
    if (String(it.type || "").toLowerCase() === "folder") {
      continue;
    }
    const token = String(it.token || "").trim();
    if (!token) {
      continue;
    }
    candidates.push(it);
  }

  const stats = {
    requested: candidates.length,
    queried_chunks: 0,
    failed_chunks: 0,
    enriched_rows: 0,
    errors: [],
  };
  if (candidates.length === 0) {
    return stats;
  }

  const chunkSize = 50;
  for (let i = 0; i < candidates.length; i += chunkSize) {
    const chunk = candidates.slice(i, i + chunkSize);
    const requestDocs = chunk.map((it) => ({
      doc_token: String(it.token || ""),
      doc_type: metaDocType(it.type),
    }));
    const payload = { request_docs: requestDocs };
    try {
      const res = runLarkCli(
        ["api", "POST", "/open-apis/drive/v1/metas/batch_query", "--data", JSON.stringify(payload)],
        180000,
      );
      stats.queried_chunks += 1;
      const metas = Array.isArray(res.metas) ? res.metas : [];
      const metaMap = new Map();
      for (const m of metas) {
        const token = String(m.doc_token || "").trim();
        if (!token) {
          continue;
        }
        metaMap.set(token, m);
      }
      for (const it of chunk) {
        const token = String(it.token || "").trim();
        const meta = metaMap.get(token);
        if (!meta) {
          continue;
        }
        const modified = String(meta.latest_modify_time || "").trim();
        const created = String(meta.create_time || "").trim();
        if (modified) {
          it.modified_time = modified;
        }
        if (created) {
          it.created_time = created;
        }
        if (modified || created) {
          stats.enriched_rows += 1;
        }
      }
    } catch (error) {
      stats.failed_chunks += 1;
      stats.errors.push({
        chunk_start: i,
        chunk_size: chunk.length,
        error: String(error && error.message ? error.message : error),
      });
    }
  }

  return stats;
}

function mapFileType(driveType, fileName) {
  const dt = String(driveType || "").toLowerCase();
  if (["doc", "docx", "sheet", "bitable", "wiki", "slides", "mindnote"].includes(dt)) {
    return dt;
  }
  if (dt === "file") {
    const ext = path.extname(fileName || "").toLowerCase().replace(/^\./, "");
    return ext || "unknown";
  }
  return dt || "unknown";
}

function normalizeItem(item) {
  const token = String(item.doc_token || item.token || "").trim();
  if (!token) {
    return null;
  }
  const name = String(item.original_name || item.name || "").trim();
  const fileType = mapFileType(item.file_type || item.type, name);
  const modified = String(item.feishu_updated_at || item.modified_time || item.edit_time || "").trim();
  const created = String(item.created_at || item.created_time || item.create_time || "").trim();
  const pathSegments = Array.isArray(item.feishu_path_segments)
    ? item.feishu_path_segments.map((x) => String(x))
    : Array.isArray(item._feishu_path_segments)
      ? item._feishu_path_segments.map((x) => String(x))
      : [];
  const feishuPath = String(item.feishu_path || item._feishu_path || "").trim();

  return {
    doc_token: token,
    original_name: name || `${token}.bin`,
    file: `${token}_${sanitizeFilename(name || token)}`,
    file_type: fileType,
    source_type: "drive",
    feishu_updated_at: modified,
    feishu_created_at: created,
    feishu_path: feishuPath,
    feishu_path_segments: pathSegments,
    discovered_at: nowIso(),
  };
}

function loadInventoryFromFile(filePath) {
  const rows = readJsonl(filePath);
  return rows.map(normalizeItem).filter(Boolean);
}

function loadInventoryLive(source) {
  const folderToken = extractFolderToken(source);
  const errors = [];
  const raw = walkDriveFolder(folderToken, "", 0, errors);
  const meta = enrichItemsWithMetadata(raw);
  return {
    items: raw.map(normalizeItem).filter(Boolean),
    walkErrors: errors,
    metaStats: meta,
  };
}

function resetToPendingDownload(next, existing) {
  const out = {
    ...existing,
    ...next,
    stage: "pending_download",
    retry_download: 0,
    retry_parse: 0,
    retry_archive: 0,
    last_error: "",
    download_path: "",
    abs_download_path: "",
    parsed_path: "",
    abs_parsed_path: "",
    archived_source_path: "",
    abs_archived_source_path: "",
    archived_parsed_path: "",
    abs_archived_parsed_path: "",
    updated_at: nowIso(),
  };
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const workspace = path.resolve(args.workspace);
  const { syncRoot, stateFile: defaultStateFile, logsRoot } = resolvePaths(workspace);
  const stateFile = args.stateFile ? path.resolve(args.stateFile) : defaultStateFile;
  const runId = `stage1-${nextRunId()}`;

  ensureDir(path.resolve(syncRoot, "staging", "inventory"));
  ensureDir(path.dirname(stateFile));
  ensureDir(logsRoot);

  const lock = args.dryRun ? null : acquireStateLock(stateFile);
  try {
    return runInventory(args, syncRoot, stateFile, logsRoot, runId);
  } finally {
    releaseStateLock(lock);
  }
}

function runInventory(args, syncRoot, stateFile, logsRoot, runId) {
  const stateMap = loadStateMap(stateFile);
  const existedBefore = fs.existsSync(stateFile);
  let inventory = [];
  let walkErrors = [];
  let metaStats = {
    requested: 0,
    queried_chunks: 0,
    failed_chunks: 0,
    enriched_rows: 0,
    errors: [],
  };
  if (args.inventoryFile) {
    inventory = loadInventoryFromFile(path.resolve(args.inventoryFile));
  } else {
    const result = loadInventoryLive(args.source);
    inventory = result.items;
    walkErrors = result.walkErrors;
    metaStats = result.metaStats || metaStats;
  }

  const tempInventoryPath = path.resolve(syncRoot, "staging", "inventory", `${runId}.jsonl`);
  if (!args.dryRun) {
    writeJsonlAtomic(tempInventoryPath, inventory);
  }

  const counts = {
    discovered: inventory.length,
    created_pending_download: 0,
    reset_to_pending_download: 0,
    unchanged: 0,
    timestamp_backfilled_keep_stage: 0,
    source_timestamp_missing_keep_stage: 0,
    duplicate_token_ignored: 0,
    marked_seen: 0,
    walk_errors: walkErrors.length,
    metadata_requested: metaStats.requested,
    metadata_queried_chunks: metaStats.queried_chunks,
    metadata_failed_chunks: metaStats.failed_chunks,
    metadata_enriched_rows: metaStats.enriched_rows,
  };

  const seen = new Set();
  for (const item of inventory) {
    const token = item.doc_token;
    if (seen.has(token)) {
      counts.duplicate_token_ignored += 1;
      continue;
    }
    seen.add(token);

    const existing = stateMap.get(token);
    if (!existing) {
      const created = resetToPendingDownload(item, {});
      created.seen_in_last_scan = runId;
      created.seen_at = nowIso();
      stateMap.set(token, created);
      counts.created_pending_download += 1;
      counts.marked_seen += 1;
      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: "inventory_create_pending_download",
        from_stage: "",
        to_stage: "pending_download",
      });
      if (!args.dryRun) {
        saveStateMap(stateFile, stateMap);
      }
      continue;
    }

    const existingTs = String(existing.feishu_updated_at || "").trim();
    const incomingTs = String(item.feishu_updated_at || "").trim();

    // Migration-safe behavior:
    // 1) If source timestamp is missing, we cannot prove remote change -> keep stage.
    // 2) If existing timestamp is empty but source now has one, backfill only -> keep stage.
    if (!incomingTs) {
      existing.seen_in_last_scan = runId;
      existing.seen_at = nowIso();
      stateMap.set(token, existing);
      counts.unchanged += 1;
      counts.source_timestamp_missing_keep_stage += 1;
      counts.marked_seen += 1;
      continue;
    }
    if (!existingTs && incomingTs) {
      existing.original_name = item.original_name || existing.original_name;
      existing.file = item.file || existing.file;
      existing.file_type = item.file_type || existing.file_type;
      existing.feishu_updated_at = incomingTs;
      existing.feishu_created_at = item.feishu_created_at || existing.feishu_created_at || "";
      existing.feishu_path = item.feishu_path || existing.feishu_path || "";
      existing.feishu_path_segments = Array.isArray(item.feishu_path_segments)
        ? item.feishu_path_segments
        : existing.feishu_path_segments || [];
      existing.seen_in_last_scan = runId;
      existing.seen_at = nowIso();
      existing.updated_at = nowIso();
      stateMap.set(token, existing);
      counts.unchanged += 1;
      counts.timestamp_backfilled_keep_stage += 1;
      counts.marked_seen += 1;
      continue;
    }

    if (existingTs === incomingTs) {
      existing.seen_in_last_scan = runId;
      existing.seen_at = nowIso();
      stateMap.set(token, existing);
      counts.unchanged += 1;
      counts.marked_seen += 1;
      continue;
    }

    const reset = resetToPendingDownload(item, existing);
    reset.seen_in_last_scan = runId;
    reset.seen_at = nowIso();
    stateMap.set(token, reset);
    counts.reset_to_pending_download += 1;
    counts.marked_seen += 1;
    appendEvent(logsRoot, {
      run_id: runId,
      ts: nowIso(),
      doc_token: token,
      event_type: "inventory_reset_pending_download",
      from_stage: String(existing.stage || ""),
      to_stage: "pending_download",
      reason: "feishu_updated_at_changed",
    });
    if (!args.dryRun) {
      saveStateMap(stateFile, stateMap);
    }
  }

  // Flush any unchanged-row mark updates in a single write.
  if (!args.dryRun) {
    saveStateMap(stateFile, stateMap);
  }

  // Emit walk errors as events so they are visible in logs/events/*.jsonl.
  for (const e of walkErrors) {
    appendEvent(logsRoot, {
      run_id: runId,
      ts: nowIso(),
      event_type: "inventory_walk_partial_failure",
      ...e,
    });
  }
  for (const e of metaStats.errors || []) {
    appendEvent(logsRoot, {
      run_id: runId,
      ts: nowIso(),
      event_type: "inventory_meta_partial_failure",
      ...e,
    });
  }

  const receipt = {
    stage: "stage1_inventory_v2",
    ok: walkErrors.length === 0 && metaStats.failed_chunks === 0,
    run_id: runId,
    dry_run: args.dryRun,
    source: args.source,
    inventory_file: tempInventoryPath,
    state_file: stateFile,
    state_file_preexisted: existedBefore,
    ...counts,
    next_stage_allowed: true,
  };
  if (!args.dryRun) {
    writeRunLog(logsRoot, runId, receipt);
  }
  console.log(JSON.stringify(receipt, null, 2));
  // Partial walk failure → non-zero exit so the pipeline does NOT proceed on
  // an incomplete inventory and silently miss state resets.
  return receipt.ok ? 0 : 2;
}

try {
  process.exit(main());
} catch (error) {
  console.log(
    JSON.stringify(
      {
        stage: "stage1_inventory_v2",
        ok: false,
        error: String(error && error.message ? error.message : error),
      },
      null,
      2,
    ),
  );
  process.exit(1);
}
