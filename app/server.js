#!/usr/bin/env node
"use strict";

// Local-only UI/API for the canonical flow runner. No daemon, dashboard, ffmpeg,
// or browser-driver package: each run owns one bounded cdp.py JSONL child process.
const http = require("http");
const fs = require("fs");
const fsp = fs.promises;
const path = require("path");
const { spawn } = require("child_process");
const crypto = require("crypto");

const ROOT = path.resolve(__dirname, "..");
const PUBLIC = path.join(__dirname, "public");
const FLOWS = path.join(ROOT, "examples");
const RUNS = path.join(ROOT, "runs");
const RUNNER = path.join(ROOT, "scripts", "flow-runner.py");
const HOST = "127.0.0.1";
const PORT = Number(process.env.QA_PORT || 4173);
const PYTHON = process.env.PYTHON || (process.platform === "win32" ? "py" : "python3");
const MAX_BODY = 1024 * 1024;
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;
const runs = new Map();

function json(res, status, value) {
  const body = JSON.stringify(value);
  res.writeHead(status, {"Content-Type": "application/json; charset=utf-8", "Content-Length": Buffer.byteLength(body)});
  res.end(body);
}

function safeId(value, label = "id") {
  if (typeof value !== "string" || !SAFE_ID.test(value)) throw Object.assign(new Error(`invalid ${label}`), {status: 400});
  return value;
}

function childJson(args, stdin) {
  return new Promise((resolve, reject) => {
    const child = spawn(PYTHON, [RUNNER, ...args], {cwd: ROOT, windowsHide: true, stdio: ["pipe", "pipe", "pipe"]});
    let out = "", err = "";
    child.stdout.on("data", chunk => { if (out.length < MAX_BODY) out += chunk; });
    child.stderr.on("data", chunk => { if (err.length < MAX_BODY) err += chunk; });
    child.on("error", reject);
    child.on("close", code => {
      try {
        const lines = out.trim().split(/\r?\n/).filter(Boolean);
        const value = JSON.parse(lines[lines.length - 1] || "{}");
        if (code !== 0) return reject(Object.assign(new Error(value.error?.message || err || `runner exit ${code}`), {detail: value}));
        resolve(value);
      } catch (error) { reject(Object.assign(error, {detail: {stdout: out.slice(-2000), stderr: err.slice(-2000)}})); }
    });
    child.stdin.end(stdin || "");
  });
}

async function flowFiles() {
  const names = await fsp.readdir(FLOWS);
  return names.filter(name => /\.ya?ml$/i.test(name)).sort();
}

async function metadata(id, full = false) {
  safeId(id, "flow id");
  const candidates = (await flowFiles()).filter(name => path.parse(name).name === id);
  if (candidates.length !== 1) throw Object.assign(new Error("flow not found"), {status: 404});
  return childJson(["--flow", path.join(FLOWS, candidates[0]), "--meta", ...(full ? ["--full"] : [])]);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", chunk => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(Object.assign(new Error("request body too large"), {status: 413}));
        req.destroy();
      } else chunks.push(chunk);
    });
    req.on("end", () => {
      try { resolve(JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}")); }
      catch { reject(Object.assign(new Error("invalid JSON body"), {status: 400})); }
    });
    req.on("error", reject);
  });
}

function publish(run, event) {
  run.events.push(event);
  if (run.events.length > 5000) run.events.shift();
  const line = `data: ${JSON.stringify(event)}\n\n`;
  for (const client of run.clients) client.write(line);
}

function startRun(body) {
  const flow = safeId(body.flow, "flow");
  const targetId = body.target_id || process.env.TGT_ID;
  if (!targetId || typeof targetId !== "string") throw Object.assign(new Error("target_id is required"), {status: 400});
  if (body.vars != null && (typeof body.vars !== "object" || Array.isArray(body.vars))) {
    throw Object.assign(new Error("vars must be an object"), {status: 400});
  }
  const runId = `${Date.now()}-${crypto.randomBytes(4).toString("hex")}`;
  const flowPath = path.join(FLOWS, `${flow}.yaml`);
  if (!fs.existsSync(flowPath)) throw Object.assign(new Error("flow not found"), {status: 404});
  const args = ["--flow", flowPath, "--out", path.join(RUNS, runId), "--vars-json", "-", "--target-id", targetId];
  if (process.env.TEIBTO_CDP_SCRIPT) args.push("--cdp-script", process.env.TEIBTO_CDP_SCRIPT);
  if (process.env.CDP_PORT) args.push("--cdp-port", process.env.CDP_PORT);
  const child = spawn(PYTHON, [RUNNER, ...args], {cwd: ROOT, windowsHide: true, stdio: ["pipe", "pipe", "pipe"]});
  const run = {id: runId, child, clients: new Set(), events: [], buffer: "", stderr: "", closed: false};
  runs.set(runId, run);
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", chunk => {
    run.buffer += chunk;
    const lines = run.buffer.split(/\r?\n/);
    run.buffer = lines.pop();
    for (const line of lines) {
      if (!line.trim()) continue;
      try { publish(run, JSON.parse(line)); }
      catch { publish(run, {type: "fatal", error: {code: "INVALID_RUNNER_EVENT", message: "runner emitted non-JSON output"}}); }
    }
  });
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", chunk => { run.stderr = (run.stderr + chunk).slice(-4000); });
  child.on("error", error => publish(run, {type: "fatal", error: {code: "RUNNER_START_FAILED", message: error.message}}));
  child.on("close", code => {
    run.closed = true;
    publish(run, {type: "closed", code, ok: code === 0, ...(run.stderr ? {stderr: run.stderr} : {})});
    for (const client of run.clients) client.end();
    run.clients.clear();
    if (runs.size > 100) {
      for (const [oldId, oldRun] of runs) {
        if (runs.size <= 100) break;
        if (oldRun.closed) runs.delete(oldId);
      }
    }
  });
  child.stdin.end(JSON.stringify(body.vars || {}));
  return runId;
}

async function saveFlow(id, yamlText) {
  safeId(id, "flow id");
  if (typeof yamlText !== "string" || !yamlText.trim() || Buffer.byteLength(yamlText) > MAX_BODY) {
    throw Object.assign(new Error("yaml is required and must be <= 1 MB"), {status: 400});
  }
  await fsp.mkdir(RUNS, {recursive: true});
  const temp = path.join(RUNS, `.validate-${Date.now()}-${crypto.randomBytes(4).toString("hex")}.yaml`);
  try {
    await fsp.writeFile(temp, yamlText, {encoding: "utf8", flag: "wx"});
    const meta = await childJson(["--flow", temp, "--meta"]);
    if (meta.id !== id) throw Object.assign(new Error("story field must match URL id"), {status: 400});
    await fsp.writeFile(path.join(FLOWS, `${id}.yaml`), yamlText, {encoding: "utf8", flag: "w"});
    return meta;
  } finally {
    await fsp.rm(temp, {force: true});
  }
}

async function handler(req, res) {
  const url = new URL(req.url, `http://${HOST}:${PORT}`);
  if (req.method === "GET" && url.pathname === "/api/health") {
    return json(res, 200, {ok: true, runner: "cdp-jsonl", target_pinned: Boolean(process.env.TGT_ID), record: false});
  }
  if (req.method === "GET" && url.pathname === "/api/stories") {
    const items = [];
    for (const file of await flowFiles()) items.push(await metadata(path.parse(file).name));
    return json(res, 200, items);
  }
  let match = url.pathname.match(/^\/api\/stories\/([A-Za-z0-9_-]+)$/);
  if (match && req.method === "GET") return json(res, 200, await metadata(match[1], true));
  if (match && req.method === "PUT") {
    const body = await readBody(req);
    return json(res, 200, await saveFlow(match[1], body.yaml));
  }
  if (req.method === "POST" && url.pathname === "/api/run") {
    const body = await readBody(req);
    return json(res, 202, {run_id: startRun(body)});
  }
  match = url.pathname.match(/^\/api\/events\/([A-Za-z0-9-]+)$/);
  if (match && req.method === "GET") {
    const run = runs.get(match[1]);
    if (!run) return json(res, 404, {error: "run not found"});
    res.writeHead(200, {"Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive"});
    for (const event of run.events) res.write(`data: ${JSON.stringify(event)}\n\n`);
    if (run.closed) return res.end();
    run.clients.add(res);
    req.on("close", () => run.clients.delete(res));
    return;
  }
  match = url.pathname.match(/^\/api\/runs\/([A-Za-z0-9-]+)\/cancel$/);
  if (match && req.method === "POST") {
    const run = runs.get(match[1]);
    if (!run) return json(res, 404, {error: "run not found"});
    if (!run.closed) run.child.kill("SIGTERM");
    return json(res, 202, {ok: true});
  }
  match = url.pathname.match(/^\/runs\/([A-Za-z0-9-]+)\/(qa-report\.md|shots\/[A-Za-z0-9_.-]+\.png)$/);
  if (match && req.method === "GET") {
    const artifact = path.resolve(RUNS, match[1], match[2]);
    const runRoot = path.resolve(RUNS, match[1]) + path.sep;
    if (!artifact.startsWith(runRoot)) return json(res, 400, {error: "invalid artifact path"});
    let body;
    try { body = await fsp.readFile(artifact); } catch { return json(res, 404, {error: "artifact not found"}); }
    const type = artifact.endsWith(".png") ? "image/png" : "text/markdown; charset=utf-8";
    res.writeHead(200, {"Content-Type": type, "Content-Length": body.length, "Cache-Control": "no-store"});
    return res.end(body);
  }
  if (req.method === "GET" && (url.pathname === "/" || url.pathname === "/index.html")) {
    const body = await fsp.readFile(path.join(PUBLIC, "index.html"));
    res.writeHead(200, {"Content-Type": "text/html; charset=utf-8", "Content-Length": body.length});
    return res.end(body);
  }
  return json(res, 404, {error: "not found"});
}

fsp.mkdir(RUNS, {recursive: true}).then(() => {
  http.createServer((req, res) => handler(req, res).catch(error => {
    console.error(error);
    if (!res.headersSent) json(res, error.status || 500, {error: error.message, ...(error.detail ? {detail: error.detail} : {})});
    else res.end();
  })).listen(PORT, HOST, () => {
    console.log(`TEIBTO Browser QA UI: http://${HOST}:${PORT}`);
    console.log("Driver: one pinned cdp.py JSONL session per run");
  });
}).catch(error => { console.error(error); process.exit(1); });
