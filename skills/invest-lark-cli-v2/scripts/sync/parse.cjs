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
  saveStateMap,
  toDataRelativePath,
  writeRunLog,
} = require("../lib/common.cjs");

const VALID_CONVERTERS = new Set(["auto", "opendataloader", "cli", "mock"]);
const DEFAULT_WORKSPACE = path.resolve(__dirname, "../../../../");

// Dynamic PDF timeout and oversized skip — mirrors the fix that v1 needed.
const OVERSIZED_MB = 50;
const TIMEOUT_FLOOR_MS = 120_000;
const TIMEOUT_CEIL_MS = 1_500_000;
const TIMEOUT_PER_MB_MS = 45_000;

function pdfTimeoutMs(bytes) {
  const mb = Math.max(bytes / 1024 / 1024, 0.1);
  return Math.min(Math.max(TIMEOUT_FLOOR_MS, mb * TIMEOUT_PER_MB_MS), TIMEOUT_CEIL_MS);
}

function printHelp() {
  console.log(
    [
      "Usage:",
      "  node skills/invest-lark-cli-v2/scripts/sync/parse.cjs [options]",
      "",
      "Options:",
      `  --workspace /abs/workspace              # optional, default: ${DEFAULT_WORKSPACE}`,
      "  --state-file /abs/path/doc_states.jsonl",
      "  --parsed-dir /abs/path/parsed",
      "  --converter auto|cli|mock (default: auto)",
      "  --max-retries 3",
    ].join("\n"),
  );
}

function parseArgs(argv) {
  const out = {
    workspace: DEFAULT_WORKSPACE,
    stateFile: "",
    parsedDir: "",
    converter: "auto",
    maxRetries: 3,
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
    } else if (arg === "--parsed-dir") {
      out.parsedDir = String(argv[i + 1] || "").trim();
      i += 1;
    } else if (arg === "--converter") {
      out.converter = String(argv[i + 1] || "").trim().toLowerCase();
      i += 1;
    } else if (arg === "--max-retries") {
      out.maxRetries = Number.parseInt(String(argv[i + 1] || "3"), 10);
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
  if (!VALID_CONVERTERS.has(out.converter)) {
    throw new Error(`Invalid --converter: ${out.converter}`);
  }
  if (!Number.isInteger(out.maxRetries) || out.maxRetries < 1) {
    throw new Error("--max-retries must be an integer >= 1");
  }
  return out;
}

function resolveAbsDownloadPath(row, dataRoot) {
  const abs = String(row.abs_download_path || "").trim();
  if (abs) {
    return path.resolve(abs);
  }
  const relRaw = String(row.download_path || "").trim();
  if (!relRaw) {
    return "";
  }
  if (path.isAbsolute(relRaw)) {
    return path.resolve(relRaw);
  }
  const rel = relRaw.replace(/\\/g, "/");
  if (rel.startsWith("lark_sync_v2/")) {
    return path.resolve(dataRoot, rel);
  }
  return path.resolve(dataRoot, "lark_sync_v2", "staging", rel);
}

function candidateFileSize(row, dataRoot) {
  const absPath = resolveAbsDownloadPath(row, dataRoot);
  if (!absPath) {
    return Number.MAX_SAFE_INTEGER;
  }
  try {
    const st = fs.statSync(absPath);
    if (!st.isFile()) {
      return Number.MAX_SAFE_INTEGER;
    }
    return Number.isFinite(st.size) ? st.size : Number.MAX_SAFE_INTEGER;
  } catch {
    return Number.MAX_SAFE_INTEGER;
  }
}

function isMarkdownType(fileType, absPath) {
  const ft = String(fileType || "").toLowerCase();
  if (ft === "md" || ft === "markdown") {
    return true;
  }
  const ext = path.extname(absPath).toLowerCase();
  return ext === ".md" || ext === ".markdown";
}

function isPdfType(fileType, absPath) {
  const ft = String(fileType || "").toLowerCase();
  if (ft === "pdf") {
    return true;
  }
  return path.extname(absPath).toLowerCase() === ".pdf";
}

function findGeneratedMarkdown(outputDir, sourcePath) {
  const expected = path.join(
    outputDir,
    `${path.basename(sourcePath, path.extname(sourcePath))}.md`,
  );
  if (fs.existsSync(expected)) {
    return expected;
  }
  const stack = [outputDir];
  const lowerStem = path.basename(sourcePath, path.extname(sourcePath)).toLowerCase();
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current || !fs.existsSync(current)) {
      continue;
    }
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(full);
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      if (path.extname(entry.name).toLowerCase() !== ".md") {
        continue;
      }
      if (entry.name.toLowerCase().startsWith(lowerStem)) {
        return full;
      }
    }
  }
  throw new Error(`No markdown output generated for ${sourcePath}`);
}

function convertWithOpenDataLoaderCli(sourcePath, outputDir, timeoutMs) {
  const cmd = [sourcePath, "-o", outputDir, "-f", "markdown", "--quiet"];
  const result = spawnSync("opendataloader-pdf", cmd, {
    encoding: "utf-8",
    timeout: timeoutMs,
    killSignal: "SIGKILL",
  });
  if (result.error) {
    const sig = result.signal ? ` signal=${result.signal}` : "";
    throw new Error(`opendataloader-pdf execution failed${sig}: ${result.error.message}`);
  }
  if (result.signal) {
    throw new Error(`opendataloader-pdf killed by ${result.signal} (timeout=${timeoutMs}ms)`);
  }
  if (result.status !== 0) {
    throw new Error(
      `opendataloader-pdf exit=${result.status}: ${
        (result.stderr || result.stdout || "").trim() || "unknown error"
      }`,
    );
  }
  return findGeneratedMarkdown(outputDir, sourcePath);
}

function convertWithMock(sourcePath, outputDir) {
  const outputPath = path.join(
    outputDir,
    `${path.basename(sourcePath, path.extname(sourcePath))}.md`,
  );
  const content = [
    `# Mock conversion for ${path.basename(sourcePath)}`,
    "",
    "This markdown was generated by parse.cjs mock converter.",
    "",
    `source: ${sourcePath}`,
    "",
  ].join("\n");
  ensureDir(path.dirname(outputPath));
  fs.writeFileSync(outputPath, content, "utf-8");
  return outputPath;
}

function convertPdf(sourcePath, outputDir, converter, timeoutMs) {
  if (converter === "mock") {
    return convertWithMock(sourcePath, outputDir);
  }
  // Both `auto` and `opendataloader` now route to the CLI: it's the only path
  // where we can enforce a hard timeout via spawnSync.
  return convertWithOpenDataLoaderCli(sourcePath, outputDir, timeoutMs);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const workspace = path.resolve(args.workspace);
  const { dataRoot, syncRoot, stateFile: defaultStateFile, logsRoot } = resolvePaths(workspace);
  const stateFile = args.stateFile ? path.resolve(args.stateFile) : defaultStateFile;
  const parsedRoot = args.parsedDir
    ? path.resolve(args.parsedDir)
    : path.resolve(syncRoot, "staging", "parsed");
  const runId = `stage3-${nextRunId()}`;
  ensureDir(path.dirname(stateFile));
  ensureDir(logsRoot);
  ensureDir(parsedRoot);

  const lock = args.dryRun ? null : acquireStateLock(stateFile);
  try {
    return runParse(args, dataRoot, stateFile, parsedRoot, logsRoot, runId);
  } finally {
    releaseStateLock(lock);
  }
}

function runParse(args, dataRoot, stateFile, parsedRoot, logsRoot, runId) {

  const stateMap = loadStateMap(stateFile);
  const candidates = [];
  for (const row of stateMap.values()) {
    if (["pending_parse", "failed_parse"].includes(String(row.stage || ""))) {
      candidates.push(row);
    }
  }
  // Small-file-first to reduce long-tail blocking from huge PDFs.
  candidates.sort((a, b) => candidateFileSize(a, dataRoot) - candidateFileSize(b, dataRoot));

  const counts = {
    total: stateMap.size,
    processed: 0,
    pending_archive: 0,
    no_parse_required: 0,
    oversized_skip: 0,
    failed_parse: 0,
    frozen_parse: 0,
    skipped: stateMap.size - candidates.length,
  };

  for (const row of candidates) {
    const token = String(row.doc_token || "").trim();
    if (!token) {
      continue;
    }

    const retry = Number.parseInt(String(row.retry_parse || 0), 10);
    if (Number.isFinite(retry) && retry >= args.maxRetries && row.stage === "failed_parse") {
      row.stage = "frozen_parse";
      row.updated_at = nowIso();
      counts.frozen_parse += 1;
      counts.processed += 1;
      stateMap.set(token, row);
      if (!args.dryRun) {
        saveStateMap(stateFile, stateMap);
      }
      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: "parse_frozen",
        to_stage: "frozen_parse",
      });
      continue;
    }

    const fromStage = String(row.stage || "");
    try {
      const absDownloadPath = resolveAbsDownloadPath(row, dataRoot);
      if (!absDownloadPath || !fs.existsSync(absDownloadPath)) {
        throw new Error(`Download path missing: ${absDownloadPath || "(empty)"}`);
      }

      if (isMarkdownType(row.file_type, absDownloadPath)) {
        const outDir = path.join(parsedRoot, token);
        const outPath = path.join(outDir, path.basename(absDownloadPath));
        if (!args.dryRun) {
          ensureDir(path.dirname(outPath));
          fs.copyFileSync(absDownloadPath, outPath);
        }
        row.stage = "pending_archive";
        row.parse_method = "copy";
        row.parsed_path = toDataRelativePath(dataRoot, outPath);
        row.abs_parsed_path = outPath;
        row.last_error = "";
        row.updated_at = nowIso();
        counts.pending_archive += 1;
      } else if (isPdfType(row.file_type, absDownloadPath)) {
        const sizeBytes = fs.statSync(absDownloadPath).size;
        const sizeMb = sizeBytes / 1024 / 1024;
        if (sizeMb > OVERSIZED_MB) {
          // Skip parse; archive will only carry the source file.
          row.stage = "pending_archive";
          row.parse_method = "oversized_skip";
          row.parsed_path = "";
          row.abs_parsed_path = "";
          row.last_error = "";
          row.note = `oversized_${Math.round(sizeMb)}MB_source_only`;
          row.updated_at = nowIso();
          counts.pending_archive += 1;
          counts.oversized_skip += 1;
          appendEvent(logsRoot, {
            run_id: runId,
            ts: nowIso(),
            doc_token: token,
            event_type: "parse_oversized_skip",
            from_stage: fromStage,
            to_stage: "pending_archive",
            size_mb: Math.round(sizeMb),
          });
        } else {
          const outDir = path.join(parsedRoot, token);
          const timeoutMs = pdfTimeoutMs(sizeBytes);
          let outPath;
          if (args.dryRun) {
            outPath = path.join(
              outDir,
              `${path.basename(absDownloadPath, path.extname(absDownloadPath))}.md`,
            );
          } else {
            ensureDir(outDir);
            outPath = convertPdf(absDownloadPath, outDir, args.converter, timeoutMs);
          }
          row.stage = "pending_archive";
          row.parse_method = args.converter === "mock" ? "mock" : "opendataloader";
          row.parsed_path = toDataRelativePath(dataRoot, outPath);
          row.abs_parsed_path = outPath;
          row.last_error = "";
          row.updated_at = nowIso();
          counts.pending_archive += 1;
        }
      } else {
        row.stage = "no_parse_required";
        row.parse_method = "none";
        row.parsed_path = "";
        row.abs_parsed_path = "";
        row.last_error = "";
        row.updated_at = nowIso();
        counts.no_parse_required += 1;
      }

      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: "parse_success",
        from_stage: fromStage,
        to_stage: String(row.stage),
        parse_method: String(row.parse_method || ""),
      });
    } catch (error) {
      row.retry_parse = Number.parseInt(String(row.retry_parse || 0), 10) + 1;
      row.last_error = String(error.message || error);
      row.updated_at = nowIso();
      if (row.retry_parse >= args.maxRetries) {
        row.stage = "frozen_parse";
        counts.frozen_parse += 1;
      } else {
        row.stage = "failed_parse";
        counts.failed_parse += 1;
      }
      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: "parse_failed",
        from_stage: fromStage,
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

  const receipt = {
    stage: "stage3_parse_v2",
    ok: counts.failed_parse === 0 && counts.frozen_parse === 0,
    run_id: runId,
    dry_run: args.dryRun,
    converter: args.converter,
    state_file: stateFile,
    parsed_dir: parsedRoot,
    ...counts,
    next_stage_allowed: counts.pending_archive > 0,
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
        stage: "stage3_parse_v2",
        ok: false,
        error: String(error && error.message ? error.message : error),
      },
      null,
      2,
    ),
  );
  process.exit(1);
}
