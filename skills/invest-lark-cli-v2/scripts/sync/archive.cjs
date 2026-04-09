#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const {
  acquireStateLock,
  appendEvent,
  copyFileAtomic,
  ensureDir,
  loadStateMap,
  nextRunId,
  nowIso,
  readJson,
  releaseStateLock,
  resolvePaths,
  sanitizeFilename,
  saveStateMap,
  toDataRelativePath,
  writeRunLog,
} = require("../lib/common.cjs");

const DEFAULT_WORKSPACE = path.resolve(__dirname, "../../../../");

function parseArgs(argv) {
  const out = {
    workspace: DEFAULT_WORKSPACE,
    stateFile: "",
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
    } else if (arg === "--max-retries") {
      out.maxRetries = Number.parseInt(String(argv[i + 1] || "3"), 10);
      i += 1;
    } else if (arg === "--dry-run") {
      out.dryRun = true;
    } else if (arg === "-h" || arg === "--help") {
      console.log(
        [
          "Usage:",
          "  node skills/invest-lark-cli-v2/scripts/sync/archive.cjs [options]",
          "",
          "Options:",
          `  --workspace /abs/workspace              # optional, default: ${DEFAULT_WORKSPACE}`,
          "  --state-file /abs/path/doc_states.jsonl",
          "  --max-retries 3",
          "  --dry-run                               # plan only, no file writes",
        ].join("\n"),
      );
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  if (!Number.isInteger(out.maxRetries) || out.maxRetries < 1) {
    throw new Error("--max-retries must be integer >= 1");
  }
  return out;
}

function levelFromCredibility(cred) {
  const raw = String(cred || "").trim();
  const m = /^L(\d+)$/i.exec(raw);
  if (!m) {
    return 99;
  }
  return Number.parseInt(m[1], 10);
}

function containsText(haystack, needle) {
  return String(haystack || "").toLowerCase().includes(String(needle || "").toLowerCase());
}

function matchCompanyInText(text, companies) {
  for (const c of companies) {
    const id = String(c.id || "").trim().toLowerCase();
    if (!id) {
      continue;
    }
    if (containsText(text, c.name) || containsText(text, id)) {
      return id;
    }
    const aliases = Array.isArray(c.aliases) ? c.aliases : [];
    for (const alias of aliases) {
      if (containsText(text, alias)) {
        return id;
      }
    }
  }
  return "";
}

function resolveCompany(row, companies) {
  const segments = Array.isArray(row.feishu_path_segments) ? row.feishu_path_segments : [];
  for (let i = segments.length - 1; i >= 0; i -= 1) {
    const id = matchCompanyInText(segments[i], companies);
    if (id) {
      return id;
    }
  }
  const fromName = matchCompanyInText(row.original_name || row.file || "", companies);
  return fromName || "unknown";
}

function chooseDocType(row, docTypes, defaultDocTypeId) {
  const segments = Array.isArray(row.feishu_path_segments) ? row.feishu_path_segments : [];
  const fileName = String(row.original_name || row.file || "");
  let best = null;
  let bestLevel = 999;
  for (const dt of docTypes) {
    const keywords = Array.isArray(dt.keywords) ? dt.keywords : [];
    let matched = false;
    for (const kw of keywords) {
      if (!kw) {
        continue;
      }
      for (const seg of segments) {
        if (containsText(seg, kw)) {
          matched = true;
          break;
        }
      }
      if (!matched && containsText(fileName, kw)) {
        matched = true;
      }
      if (matched) {
        break;
      }
    }
    if (!matched) {
      continue;
    }
    const lvl = levelFromCredibility(dt.credibility);
    if (lvl < bestLevel) {
      bestLevel = lvl;
      best = dt;
    }
  }
  if (best) {
    return best;
  }
  const fallback =
    docTypes.find((x) => String(x.id || "") === defaultDocTypeId) ||
    docTypes[0] ||
    { id: "announcements", dir: "announcements", credibility: "L5" };
  return fallback;
}

function copyFileStrict(src, dest) {
  copyFileAtomic(src, dest);
}

function resolveArchiveBase(dataRoot, companyId, docTypeDir) {
  if (companyId === "unknown") {
    return path.resolve(dataRoot, "industry", "unclassified", "lark");
  }
  return path.resolve(dataRoot, "companies", companyId, docTypeDir);
}

function buildFeishuUrl(docToken, sourceType, fileType) {
  const token = String(docToken || "").trim();
  if (!token) {
    return "";
  }
  const st = String(sourceType || "").toLowerCase();
  const ft = String(fileType || "").toLowerCase();
  if (st === "wiki") {
    return `https://feishu.cn/wiki/${token}`;
  }
  if (ft === "doc" || ft === "docx") {
    return `https://feishu.cn/docx/${token}`;
  }
  if (ft === "sheet") {
    return `https://feishu.cn/sheets/${token}`;
  }
  if (ft === "bitable") {
    return `https://feishu.cn/base/${token}`;
  }
  return `https://feishu.cn/file/${token}`;
}

function appendIntakeLog(companyRoot, row, now) {
  const logPath = path.resolve(companyRoot, "intake_log.jsonl");
  ensureDir(path.dirname(logPath));
  const entry = {
    item_id: `${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14)}-${row.company}-${row.doc_type}`,
    ts: now,
    company: row.company,
    title: String(row.original_name || ""),
    doc_type: String(row.doc_type || ""),
    credibility: String(row.credibility || ""),
    stored_rel_path: String(row.archived_source_path || ""),
    feishu_url: String(row.feishu_url || ""),
    doc_token: String(row.doc_token || ""),
  };
  fs.appendFileSync(logPath, `${JSON.stringify(entry)}\n`, "utf-8");
}

function appendTimeline(companyRoot, row, now) {
  const timelinePath = path.resolve(companyRoot, "timeline.md");
  ensureDir(path.dirname(timelinePath));
  if (!fs.existsSync(timelinePath)) {
    const header = `# ${String(row.company || "").toUpperCase()} Business Timeline\n\n`;
    fs.writeFileSync(timelinePath, header, "utf-8");
  }
  const date = String(now).slice(0, 10);
  const lines = [
    `- [${date}] doc-routed`,
    `  - type: ${String(row.doc_type || "")} (${String(row.credibility || "")})`,
    `  - title: ${String(row.original_name || "")}`,
    `  - path: ${String(row.archived_source_path || "")}`,
  ];
  if (row.feishu_url) {
    lines.push(`  - feishu: ${row.feishu_url}`);
  }
  fs.appendFileSync(timelinePath, `${lines.join("\n")}\n`, "utf-8");
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const workspace = path.resolve(args.workspace);
  const { dataRoot, stateFile: defaultStateFile, logsRoot } = resolvePaths(workspace);
  const stateFile = args.stateFile ? path.resolve(args.stateFile) : defaultStateFile;
  const runId = `stage4-${nextRunId()}`;
  ensureDir(path.dirname(stateFile));
  ensureDir(logsRoot);

  const lock = args.dryRun ? null : acquireStateLock(stateFile);
  try {
    return runArchive(args, dataRoot, stateFile, logsRoot, runId);
  } finally {
    releaseStateLock(lock);
  }
}

function runArchive(args, dataRoot, stateFile, logsRoot, runId) {

  const companiesCfg = readJson(path.resolve(dataRoot, "references", "companies.json"), { companies: [] });
  const docTypesCfg = readJson(path.resolve(dataRoot, "references", "doc_types.json"), {
    default_doc_type: "announcements",
    doc_types: [{ id: "announcements", dir: "announcements", keywords: [] }],
  });
  const companies = Array.isArray(companiesCfg.companies) ? companiesCfg.companies : [];
  const docTypes = Array.isArray(docTypesCfg.doc_types) ? docTypesCfg.doc_types : [];
  const defaultDocTypeId = String(docTypesCfg.default_doc_type || "announcements");

  const stateMap = loadStateMap(stateFile);
  const candidates = [];
  for (const row of stateMap.values()) {
    const stage = String(row.stage || "");
    // no_parse_required is a terminal state — unknown file types are NOT archived.
    if (["pending_archive", "failed_archive"].includes(stage)) {
      candidates.push(row);
    }
  }

  const counts = {
    total: stateMap.size,
    processed: 0,
    archived: 0,
    failed_archive: 0,
    frozen_archive: 0,
    unknown_company_routed: 0,
    skipped: stateMap.size - candidates.length,
  };

  for (const row of candidates) {
    const token = String(row.doc_token || "").trim();
    if (!token) {
      continue;
    }

    const retry = Number.parseInt(String(row.retry_archive || 0), 10);
    if (String(row.stage || "") === "failed_archive" && retry >= args.maxRetries) {
      row.stage = "frozen_archive";
      row.updated_at = nowIso();
      counts.frozen_archive += 1;
      counts.processed += 1;
      stateMap.set(token, row);
      if (!args.dryRun) {
        saveStateMap(stateFile, stateMap);
      }
      continue;
    }

    try {
      const fromStage = String(row.stage || "");
      const companyId = resolveCompany(row, companies);
      const dt = chooseDocType(row, docTypes, defaultDocTypeId);
      const baseDir = resolveArchiveBase(dataRoot, companyId, String(dt.dir || dt.id || "announcements"));
      const sourceDir = path.resolve(baseDir, "source");
      ensureDir(sourceDir);

      const srcDownload = String(row.abs_download_path || "").trim();
      if (!srcDownload || !fs.existsSync(srcDownload)) {
        throw new Error(`Source file missing: ${srcDownload || "(empty)"}`);
      }
      const sourceName = sanitizeFilename(String(row.original_name || path.basename(srcDownload)));
      const archivedSource = path.resolve(sourceDir, `${token}_${sourceName}`);
      if (!args.dryRun) {
        copyFileStrict(srcDownload, archivedSource);
      }

      let archivedParsed = "";
      const srcParsed = String(row.abs_parsed_path || "").trim();
      if (String(row.stage || "") === "pending_archive" && srcParsed && fs.existsSync(srcParsed)) {
        const parsedName = sanitizeFilename(path.basename(srcParsed));
        archivedParsed = path.resolve(baseDir, `${token}_${parsedName}`);
        if (!args.dryRun) {
          copyFileStrict(srcParsed, archivedParsed);
        }
      }

      const archivedAt = nowIso();
      row.stage = "archived";
      row.company = companyId;
      row.doc_type = String(dt.id || "announcements");
      row.credibility = String(dt.credibility || "L5");
      row.feishu_url = buildFeishuUrl(row.doc_token, row.source_type, row.file_type);
      row.archived_source_path = toDataRelativePath(dataRoot, archivedSource);
      row.abs_archived_source_path = archivedSource;
      row.archived_parsed_path = archivedParsed ? toDataRelativePath(dataRoot, archivedParsed) : "";
      row.abs_archived_parsed_path = archivedParsed || "";
      row.archived_at = archivedAt;
      row.last_error = "";
      row.updated_at = archivedAt;

      // Best-effort side effects: never fail archive state on intake/timeline write.
      if (companyId !== "unknown" && !args.dryRun) {
        const companyRoot = path.resolve(dataRoot, "companies", companyId);
        try {
          appendIntakeLog(companyRoot, row, archivedAt);
        } catch (error) {
          appendEvent(logsRoot, {
            run_id: runId,
            ts: nowIso(),
            doc_token: token,
            event_type: "intake_log_failed",
            company: companyId,
            error: String(error && error.message ? error.message : error),
          });
        }
        try {
          appendTimeline(companyRoot, row, archivedAt);
        } catch (error) {
          appendEvent(logsRoot, {
            run_id: runId,
            ts: nowIso(),
            doc_token: token,
            event_type: "timeline_update_failed",
            company: companyId,
            error: String(error && error.message ? error.message : error),
          });
        }
      }

      counts.archived += 1;
      if (companyId === "unknown") {
        counts.unknown_company_routed += 1;
      }
      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: companyId === "unknown" ? "archive_success_unknown_company" : "archive_success",
        from_stage: fromStage,
        to_stage: "archived",
        company: companyId,
        doc_type: row.doc_type,
      });
    } catch (error) {
      row.retry_archive = Number.parseInt(String(row.retry_archive || 0), 10) + 1;
      row.last_error = String(error.message || error);
      row.updated_at = nowIso();
      if (row.retry_archive >= args.maxRetries) {
        row.stage = "frozen_archive";
        counts.frozen_archive += 1;
      } else {
        row.stage = "failed_archive";
        counts.failed_archive += 1;
      }
      appendEvent(logsRoot, {
        run_id: runId,
        ts: nowIso(),
        doc_token: token,
        event_type: "archive_failed",
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
    stage: "stage4_archive_v2",
    ok: counts.failed_archive === 0 && counts.frozen_archive === 0,
    run_id: runId,
    dry_run: args.dryRun,
    state_file: stateFile,
    ...counts,
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
        stage: "stage4_archive_v2",
        ok: false,
        error: String(error && error.message ? error.message : error),
      },
      null,
      2,
    ),
  );
  process.exit(1);
}
