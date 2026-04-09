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
  releaseStateLock,
  resolvePaths,
  sanitizeFilename,
  saveStateMap,
  toDataRelativePath,
  writeRunLog,
} = require("../lib/common.cjs");

const VALID_MODES = new Set(["live", "mock"]);
// Only Feishu native docs should use `docs +fetch`.
// Plain markdown files in Drive (type=md/markdown) must use `drive +download`.
const FETCH_DOC_TYPES = new Set(["doc", "docx", "wiki"]);
// Types we know lark-cli cannot download through the generic file path.
// These are frozen immediately at download time instead of burning retries.
const UNSUPPORTED_DOC_TYPES = new Set(["sheet", "bitable", "slides", "mindnote"]);
const DEFAULT_WORKSPACE = path.resolve(__dirname, "../../../../");
// Hard ceiling for a single lark-cli invocation. Not size-adaptive because
// download is I/O bound and sensitive to API hangs, not to file size.
const DOWNLOAD_TIMEOUT_MS = 300_000;

function parseArgs(argv) {
  const out = {
    workspace: DEFAULT_WORKSPACE,
    stateFile: "",
    downloadMode: "live",
    maxRetries: 3,
    mockFailTokens: new Set(),
    dryRun: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--workspace") {
      out.workspace = String(argv[i + 1] || "").trim();
      i += 1;
    } else if (arg === "--state-file") {
      out.stateFile = String(argv[i + 1] || "").trim();
      i += 1;
    } else if (arg === "--download-mode") {
      out.downloadMode = String(argv[i + 1] || "").trim().toLowerCase();
      i += 1;
    } else if (arg === "--max-retries") {
      out.maxRetries = Number.parseInt(String(argv[i + 1] || "3"), 10);
      i += 1;
    } else if (arg === "--mock-fail-tokens") {
      const raw = String(argv[i + 1] || "").trim();
      i += 1;
      out.mockFailTokens = new Set(
        raw
          .split(",")
          .map((x) => x.trim())
          .filter(Boolean),
      );
    } else if (arg === "--dry-run") {
      out.dryRun = true;
    } else if (arg === "-h" || arg === "--help") {
      console.log(
        [
          "Usage:",
          "  node skills/invest-lark-cli-v2/scripts/sync/download.cjs [options]",
          "",
          "Options:",
          `  --workspace /abs/workspace              # optional, default: ${DEFAULT_WORKSPACE}`,
          "  --state-file /abs/path/doc_states.jsonl",
          "  --download-mode live|mock (default: live)",
          "  --mock-fail-tokens token1,token2",
          "  --max-retries 3",
        ].join("\n"),
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!VALID_MODES.has(out.downloadMode)) {
    throw new Error(`Invalid --download-mode: ${out.downloadMode}`);
  }
  if (!Number.isInteger(out.maxRetries) || out.maxRetries < 1) {
    throw new Error("--max-retries must be integer >= 1");
  }
  return out;
}

function runCommand(cmd, cwd = "") {
  const result = spawnSync(cmd[0], cmd.slice(1), {
    encoding: "utf-8",
    cwd: cwd || undefined,
    timeout: DOWNLOAD_TIMEOUT_MS,
    killSignal: "SIGKILL",
  });
  if (result.error) {
    const sig = result.signal ? ` signal=${result.signal}` : "";
    throw new Error(`${cmd[0]} failed${sig}: ${result.error.message}`);
  }
  if (result.signal) {
    throw new Error(`${cmd[0]} killed by ${result.signal} (timeout=${DOWNLOAD_TIMEOUT_MS}ms)`);
  }
  if (result.status !== 0) {
    throw new Error(`${cmd[0]} exit=${result.status}: ${(result.stderr || "").trim()}`);
  }
  return result.stdout || "";
}

function downloadLive(row, outputPath) {
  const token = String(row.doc_token || "").trim();
  const fileType = String(row.file_type || "").toLowerCase();
  if (FETCH_DOC_TYPES.has(fileType)) {
    const out = runCommand(["lark-cli", "docs", "+fetch", "--doc", token]);
    fs.writeFileSync(outputPath, out, "utf-8");
    return;
  }
  runCommand(
    ["lark-cli", "drive", "+download", "--file-token", token, "--output", path.basename(outputPath), "--overwrite"],
    path.dirname(outputPath),
  );
}

function downloadMock(row, outputPath, failTokens) {
  const token = String(row.doc_token || "").trim();
  if (failTokens.has(token)) {
    throw new Error(`mock download failed for ${token}`);
  }
  const fileType = String(row.file_type || "").toLowerCase();
  const content = FETCH_DOC_TYPES.has(fileType)
    ? `# Mock markdown for ${token}\n`
    : `mock binary placeholder for ${token}\n`;
  fs.writeFileSync(outputPath, content, "utf-8");
}

function targetExtension(row) {
  const fileType = String(row.file_type || "").toLowerCase();
  const original = String(row.original_name || "");
  if (FETCH_DOC_TYPES.has(fileType)) {
    return ".md";
  }
  const ext = path.extname(original).toLowerCase();
  if (ext) {
    return ext;
  }
  return fileType ? `.${fileType}` : ".bin";
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const workspace = path.resolve(args.workspace);
  const { dataRoot, syncRoot, stateFile: defaultStateFile, logsRoot } = resolvePaths(workspace);
  const stateFile = args.stateFile ? path.resolve(args.stateFile) : defaultStateFile;
  const runId = `stage2-${nextRunId()}`;
  const downloadRoot = path.resolve(syncRoot, "staging", "downloads");
  ensureDir(downloadRoot);
  ensureDir(logsRoot);
  ensureDir(path.dirname(stateFile));

  const lock = args.dryRun ? null : acquireStateLock(stateFile);
  try {
    return runDownload(args, dataRoot, stateFile, logsRoot, runId, downloadRoot);
  } finally {
    releaseStateLock(lock);
  }
}

function runDownload(args, dataRoot, stateFile, logsRoot, runId, downloadRoot) {

  const stateMap = loadStateMap(stateFile);
  const candidates = [];
  for (const row of stateMap.values()) {
    const stage = String(row.stage || "");
    if (stage === "pending_download" || stage === "failed_download") {
      candidates.push(row);
    }
  }

  const counts = {
    total: stateMap.size,
    processed: 0,
    pending_parse: 0,
    failed_download: 0,
    frozen_download: 0,
    unsupported_type_frozen: 0,
    skipped: stateMap.size - candidates.length,
  };

  for (const row of candidates) {
    const token = String(row.doc_token || "").trim();
    if (!token) {
      continue;
    }

    const fileType = String(row.file_type || "").toLowerCase();
    if (UNSUPPORTED_DOC_TYPES.has(fileType)) {
      row.stage = "frozen_download";
      row.last_error = `unsupported_type:${fileType}`;
      row.updated_at = nowIso();
      counts.frozen_download += 1;
      counts.unsupported_type_frozen += 1;
      counts.processed += 1;
      stateMap.set(token, row);
      if (!args.dryRun) {
        saveStateMap(stateFile, stateMap);
      }
      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: "download_frozen_unsupported",
        to_stage: "frozen_download",
        file_type: fileType,
      });
      continue;
    }

    const retry = Number.parseInt(String(row.retry_download || 0), 10);
    if (String(row.stage || "") === "failed_download" && retry >= args.maxRetries) {
      row.stage = "frozen_download";
      row.updated_at = nowIso();
      counts.frozen_download += 1;
      counts.processed += 1;
      stateMap.set(token, row);
      if (!args.dryRun) {
        saveStateMap(stateFile, stateMap);
      }
      continue;
    }

    try {
      const ext = targetExtension(row);
      const safeName = sanitizeFilename(String(row.original_name || token));
      const outPath = path.resolve(downloadRoot, `${token}_${path.basename(safeName, path.extname(safeName))}${ext}`);
      ensureDir(path.dirname(outPath));
      if (args.dryRun) {
        // Skip real I/O but keep state transition semantics visible.
      } else if (args.downloadMode === "mock") {
        downloadMock(row, outPath, args.mockFailTokens);
      } else {
        downloadLive(row, outPath);
      }

      row.stage = "pending_parse";
      row.download_path = toDataRelativePath(dataRoot, outPath);
      row.abs_download_path = outPath;
      row.retry_download = 0;
      row.last_error = "";
      row.updated_at = nowIso();
      counts.pending_parse += 1;
      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: "download_success",
        from_stage: "pending_download",
        to_stage: "pending_parse",
      });
    } catch (error) {
      row.retry_download = Number.parseInt(String(row.retry_download || 0), 10) + 1;
      row.last_error = String(error.message || error);
      row.updated_at = nowIso();
      if (row.retry_download >= args.maxRetries) {
        row.stage = "frozen_download";
        counts.frozen_download += 1;
      } else {
        row.stage = "failed_download";
        counts.failed_download += 1;
      }
      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: "download_failed",
        from_stage: "pending_download",
        to_stage: row.stage,
        error: row.last_error,
      });
    }

    counts.processed += 1;
    stateMap.set(token, row);
    if (!args.dryRun) {
      saveStateMap(stateFile, stateMap);
    }
  }

  // Unsupported-type freezes are expected outcomes, not failures — they must
  // not flip `ok` to false, otherwise every cron tick reports task failure.
  const unexpectedFrozen = counts.frozen_download - counts.unsupported_type_frozen;
  const receipt = {
    stage: "stage2_download_v2",
    ok: counts.failed_download === 0 && unexpectedFrozen === 0,
    run_id: runId,
    dry_run: args.dryRun,
    download_mode: args.downloadMode,
    state_file: stateFile,
    ...counts,
    next_stage_allowed: counts.pending_parse > 0,
  };
  if (!args.dryRun) {
    writeRunLog(logsRoot, runId, receipt);
  }
  console.log(JSON.stringify(receipt, null, 2));
  return receipt.ok ? 0 : 2;
}

try {
  process.exit(main());
} catch (error) {
  console.log(
    JSON.stringify(
      {
        stage: "stage2_download_v2",
        ok: false,
        error: String(error && error.message ? error.message : error),
      },
      null,
      2,
    ),
  );
  process.exit(1);
}
