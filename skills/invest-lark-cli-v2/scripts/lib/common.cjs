#!/usr/bin/env node
"use strict";

const fs = require("node:fs");
const path = require("node:path");

function nowIso() {
  return new Date().toISOString();
}

function ensureDir(dirPath) {
  fs.mkdirSync(dirPath, { recursive: true });
}

function normalizePath(value) {
  return String(value || "").replace(/\\/g, "/");
}

function sanitizeFilename(name) {
  const raw = String(name || "").trim();
  if (!raw) {
    return "unnamed";
  }
  const parsed = path.parse(raw);
  const safeStem = (parsed.name || "unnamed")
    .replace(/[^\w.-]+/g, "_")
    .replace(/^_+|_+$/g, "");
  const stem = safeStem || "unnamed";
  const ext = (parsed.ext || "").replace(/[^\w.]/g, "");
  return `${stem}${ext}`;
}

function resolveDataRoot(workspaceDir) {
  const envRoot = process.env.OPENCLAW_DATA_DIR;
  if (envRoot && String(envRoot).trim()) {
    return path.resolve(envRoot);
  }
  return path.resolve(workspaceDir, "workspace_data");
}

function resolveSyncRoot(dataRoot) {
  return path.resolve(dataRoot, "lark_sync_v2");
}

function resolvePaths(workspaceDir) {
  const dataRoot = resolveDataRoot(workspaceDir);
  const syncRoot = resolveSyncRoot(dataRoot);
  const stateFile = path.resolve(syncRoot, "state", "doc_states.jsonl");
  const logsRoot = path.resolve(syncRoot, "logs");
  return { dataRoot, syncRoot, stateFile, logsRoot };
}

function readJson(filePath, fallback = {}) {
  if (!fs.existsSync(filePath)) {
    return fallback;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  } catch {
    return fallback;
  }
}

function writeJsonAtomic(filePath, payload) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(payload, null, 2)}\n`, "utf-8");
  fs.renameSync(tmp, filePath);
}

// Copy a file atomically: write to a sibling .tmp, then rename.
// Protects against half-written files if the process is killed mid-copy.
function copyFileAtomic(src, dest) {
  ensureDir(path.dirname(dest));
  const tmp = `${dest}.tmp-${process.pid}-${Date.now()}`;
  fs.copyFileSync(src, tmp);
  fs.renameSync(tmp, dest);
}

// Mutex via exclusive directory creation. Same filesystem only.
// Holder must call releaseStateLock(lock) in a finally block.
//
// Zombie recovery: if the lock directory already exists and either
//   (a) owner.json names a pid on THIS host that no longer exists, or
//   (b) the lock is older than `staleMs`,
// we assume the previous holder died and reclaim it.
function isZombieLock(lockDir, hostname, staleMs) {
  try {
    const st = fs.statSync(lockDir);
    if (Date.now() - st.mtimeMs > staleMs) {
      return { reason: "stale_mtime", ageMs: Date.now() - st.mtimeMs };
    }
  } catch {
    return null;
  }
  try {
    const info = JSON.parse(fs.readFileSync(path.join(lockDir, "owner.json"), "utf-8"));
    if (info && info.hostname === hostname && Number.isInteger(info.pid)) {
      try {
        process.kill(info.pid, 0);
        return null; // process alive
      } catch (err) {
        if (err && err.code === "ESRCH") {
          return { reason: "dead_pid", pid: info.pid };
        }
        // EPERM means the pid exists but we can't signal it — treat as alive.
        return null;
      }
    }
  } catch {
    // owner.json missing or unreadable — fall through
  }
  return null;
}

function acquireStateLock(
  stateFile,
  { timeoutMs = 30_000, pollMs = 200, staleMs = 30 * 60 * 1000 } = {},
) {
  const lockDir = `${stateFile}.lock`;
  const os = require("node:os");
  const hostname = os.hostname();
  ensureDir(path.dirname(stateFile));
  const start = Date.now();
  while (true) {
    try {
      fs.mkdirSync(lockDir);
      const infoPath = path.join(lockDir, "owner.json");
      fs.writeFileSync(
        infoPath,
        JSON.stringify({
          pid: process.pid,
          hostname,
          ts: new Date().toISOString(),
        }),
      );
      return { lockDir };
    } catch (err) {
      if (err && err.code !== "EEXIST") {
        throw err;
      }
      const zombie = isZombieLock(lockDir, hostname, staleMs);
      if (zombie) {
        try {
          fs.rmSync(lockDir, { recursive: true, force: true });
          // Record the reclaim so it's traceable in logs.
          process.stderr.write(
            `[acquireStateLock] reclaimed zombie lock ${lockDir} (${JSON.stringify(zombie)})\n`,
          );
          continue;
        } catch {
          // Lost a race with another process reclaiming — fall through and retry.
        }
      }
      if (Date.now() - start > timeoutMs) {
        throw new Error(`acquireStateLock timeout: ${lockDir} held by another process`);
      }
      const until = Date.now() + pollMs;
      // Busy wait without blocking the event loop for too long.
      // eslint-disable-next-line no-empty
      while (Date.now() < until) {}
    }
  }
}

function releaseStateLock(lock) {
  if (!lock || !lock.lockDir) {
    return;
  }
  try {
    fs.rmSync(lock.lockDir, { recursive: true, force: true });
  } catch {
    // best effort
  }
}

function readJsonl(filePath) {
  if (!fs.existsSync(filePath)) {
    return [];
  }
  const lines = fs.readFileSync(filePath, "utf-8").split(/\r?\n/);
  const rows = [];
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      continue;
    }
    try {
      rows.push(JSON.parse(line));
    } catch {
      // skip malformed lines
    }
  }
  return rows;
}

function writeJsonlAtomic(filePath, rows) {
  ensureDir(path.dirname(filePath));
  const tmp = `${filePath}.tmp`;
  const lines = rows.map((row) => JSON.stringify(row));
  fs.writeFileSync(tmp, `${lines.join("\n")}${lines.length > 0 ? "\n" : ""}`, "utf-8");
  fs.renameSync(tmp, filePath);
}

function loadStateMap(stateFile) {
  const map = new Map();
  for (const row of readJsonl(stateFile)) {
    const token = String(row.doc_token || "").trim();
    if (!token) {
      continue;
    }
    map.set(token, row);
  }
  return map;
}

function saveStateMap(stateFile, stateMap) {
  writeJsonlAtomic(stateFile, Array.from(stateMap.values()));
}

function toDataRelativePath(dataRoot, targetPath) {
  const rel = normalizePath(path.relative(dataRoot, targetPath));
  if (!rel || rel.startsWith("..")) {
    return path.resolve(targetPath);
  }
  return rel;
}

function appendEvent(logsRoot, event) {
  const date = new Date().toISOString().slice(0, 10).replace(/-/g, "");
  const eventFile = path.resolve(logsRoot, "events", `${date}.jsonl`);
  ensureDir(path.dirname(eventFile));
  fs.appendFileSync(eventFile, `${JSON.stringify(event)}\n`, "utf-8");
}

function writeRunLog(logsRoot, runId, payload) {
  const runFile = path.resolve(logsRoot, "runs", `${runId}.json`);
  writeJsonAtomic(runFile, payload);
}

function nextRunId() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return [
    d.getFullYear(),
    pad(d.getMonth() + 1),
    pad(d.getDate()),
    "-",
    pad(d.getHours()),
    pad(d.getMinutes()),
    pad(d.getSeconds()),
  ].join("");
}

module.exports = {
  acquireStateLock,
  appendEvent,
  copyFileAtomic,
  ensureDir,
  loadStateMap,
  nextRunId,
  normalizePath,
  nowIso,
  readJson,
  readJsonl,
  releaseStateLock,
  resolvePaths,
  sanitizeFilename,
  saveStateMap,
  toDataRelativePath,
  writeJsonAtomic,
  writeJsonlAtomic,
  writeRunLog,
};
