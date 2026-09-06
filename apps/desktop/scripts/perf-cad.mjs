#!/usr/bin/env node
/**
 * Where the time goes when Hardcore opens a CAD file.
 *
 *   node scripts/perf-cad.mjs [--models a.step,b.step] [--out perf.json]
 *       [--cache-dir DIR]     the cadgen store the app's processes use
 *                             (default: a fresh temp dir, so every compile
 *                             and tessellation is a miss on the first open)
 *       [--no-app]            skip the Playwright timeline
 *       [--no-processes]      skip the cadgen process costs
 *       [--hover-ms 5000] [--orbit-ms 5000]
 *
 * Two halves, both against `npm run build`'s `out/` and whatever runtime the
 * app resolves on its own (README, CAD runtime) — the checkout's `.venv` in
 * a checkout, the bundled one after `npm run bundle:runtime`.
 *
 * THE APP TIMELINE launches the built app the way the e2e does (a throwaway
 * user-data directory, `NODE_ENV=test`), adds this repository as the project
 * and opens each model three times: COLD (a fresh store: the document has no
 * tree, no component has a cached tessellation), WARM IN SESSION (switch to
 * another tab and back: the renderer's memory caches), and WARM ACROSS
 * SESSIONS (quit, relaunch on the same user data and store: the store's tree
 * and the shared tessellation cache answer). For each open it records, from
 * the click in the file tree:
 *
 *   viewer up      main's `[viewer] started` line — the runtime probe plus the
 *                  `cadgen viewer --api-only` launch, on the first open only
 *   canvas         the surface's WebGL canvas is in the DOM
 *   first frame    the first `cad:frame` measure (the empty stage)
 *   compile        the POST /__cad/artifact round trip (a store miss compiles
 *                  the document in cadgen's pool; a hit answers at once)
 *   model painted  the loading overlay is gone and a frame has rendered
 *   sheet ready    the STEP sheet's tree is up
 *   tessellation   the `cad:tessellate` measures: per-component worker time,
 *                  split by shared-cache hit and miss
 *   interactive    the first `cad:hover-pick` measure after the pointer moves
 *   hover / orbit  `cad:hover-pick` and `cad:frame` distributions over a
 *                  scripted sweep and a scripted drag
 *
 * plus every /__cad and /__tess_cache response the page made. The measures
 * come from `cadgen-js/lib/viewer/perfMarks.js`, recorded only because this
 * script sets `globalThis.__cadgenPerf` in the page.
 *
 * THE PROCESS COSTS time, with the same interpreter and environment the app
 * gives its children: `import cadgen` (and the viewer and daemon-client
 * modules), the viewer server's launch to its JSON line, and `cadgen step
 * inspect validate` on the mid-sized model — transient vs daemon, store miss
 * vs hit, daemon first job (spawn) vs warm. The daemon it spawns listens on
 * a private socket and is killed at the end.
 *
 * Output: a Markdown summary on stdout, and the raw numbers as JSON to
 * `--out` (default `tests/perf/perf-cad.json`, gitignored).
 */
import { execFile, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import readline from "node:readline";
import { performance } from "node:perf_hooks";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { _electron as electron } from "@playwright/test";

const execFileAsync = promisify(execFile);

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(appRoot, "..", "..");

const DEFAULT_MODELS = [
  "models/examples/imported/import-smoke.step",
  "models/thang010146/STEP/imported/180_degree_flip_mechanism.step",
  "models/assemblies/STEP/mars_rover_concept/mars_rover_concept.step",
];

/* -------------------------------------------------------------------------- */
/* Arguments                                                                   */
/* -------------------------------------------------------------------------- */

function parseArgs(argv) {
  const options = {
    models: DEFAULT_MODELS,
    out: path.join(appRoot, "tests", "perf", "perf-cad.json"),
    cacheDir: null,
    app: true,
    processes: true,
    hoverMs: 5000,
    orbitMs: 5000,
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length) {
        throw new Error(`${arg} needs a value`);
      }
      return argv[index];
    };
    if (arg === "--models") {
      options.models = next().split(",").map((item) => item.trim()).filter(Boolean);
    } else if (arg === "--out") {
      options.out = path.resolve(next());
    } else if (arg === "--cache-dir") {
      options.cacheDir = path.resolve(next());
    } else if (arg === "--no-app") {
      options.app = false;
    } else if (arg === "--no-processes") {
      options.processes = false;
    } else if (arg === "--hover-ms") {
      options.hoverMs = Number(next());
    } else if (arg === "--orbit-ms") {
      options.orbitMs = Number(next());
    } else {
      throw new Error(`unknown argument ${arg}`);
    }
  }
  return options;
}

/* -------------------------------------------------------------------------- */
/* Numbers                                                                     */
/* -------------------------------------------------------------------------- */

function round(value, digits = 1) {
  if (!Number.isFinite(value)) {
    return null;
  }
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function stats(values) {
  const sorted = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!sorted.length) {
    return { count: 0 };
  }
  const at = (fraction) => sorted[Math.min(sorted.length - 1, Math.floor(fraction * sorted.length))];
  return {
    count: sorted.length,
    mean: round(sorted.reduce((sum, value) => sum + value, 0) / sorted.length, 2),
    p50: round(at(0.5), 2),
    p95: round(at(0.95), 2),
    max: round(sorted[sorted.length - 1], 2),
    total: round(sorted.reduce((sum, value) => sum + value, 0), 1),
  };
}

function fmt(ms) {
  if (!Number.isFinite(ms)) {
    return "—";
  }
  return ms >= 1000 ? `${round(ms / 1000, 2)} s` : `${round(ms, 0)} ms`;
}

function fmtStats(entry) {
  if (!entry || !entry.count) {
    return "—";
  }
  return `n=${entry.count} p50 ${fmt(entry.p50)} p95 ${fmt(entry.p95)} max ${fmt(entry.max)}`;
}

/* -------------------------------------------------------------------------- */
/* The interpreter and its environment, the way the app resolves them          */
/* -------------------------------------------------------------------------- */

function mainCheckoutOfWorktree(root) {
  const dotGit = path.join(root, ".git");
  try {
    if (!fs.statSync(dotGit).isFile()) {
      return null;
    }
    const match = /^gitdir:\s*(.+?)\s*$/m.exec(fs.readFileSync(dotGit, "utf8"));
    if (!match) {
      return null;
    }
    const gitdir = path.resolve(root, match[1]);
    const marker = `${path.sep}.git${path.sep}worktrees${path.sep}`;
    const at = gitdir.indexOf(marker);
    return at === -1 ? null : gitdir.slice(0, at);
  } catch {
    return null;
  }
}

function resolvePython() {
  const override = process.env.CAD_DESKTOP_PYTHON?.trim();
  if (override) {
    return override;
  }
  const venv = (root) => path.join(root, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  if (fs.existsSync(venv(repoRoot))) {
    return venv(repoRoot);
  }
  const main = mainCheckoutOfWorktree(repoRoot);
  if (main && fs.existsSync(venv(main))) {
    return venv(main);
  }
  throw new Error("no interpreter: set CAD_DESKTOP_PYTHON or create the checkout's .venv");
}

/**
 * A private daemon per run, so "first job" is measured against a daemon that
 * did not exist and the run's daemon can be killed at the end. The socket has
 * to be SHORT: macOS caps an AF_UNIX path at 104 bytes and a long temp path
 * makes the daemon fail to bind — silently, from the client's side, since a
 * missing daemon is the documented cold fallback. Windows names a pipe, not
 * a path, and keeps the default.
 */
let socketDir = null;
function daemonSocketEnv(name) {
  if (process.platform === "win32") {
    return {};
  }
  socketDir ??= fs.mkdtempSync("/tmp/hc-perf-");
  return { CADGEN_DAEMON_SOCKET: path.join(socketDir, `${name}.sock`) };
}

/** What `CadRuntime.processEnv` gives a checkout's cadgen child, plus this run's store and daemon. */
function cadgenEnv(extra = {}) {
  return {
    ...process.env,
    PYTHONPATH: path.join(repoRoot, "packages", "cadgen", "src"),
    PYTHONUNBUFFERED: "1",
    CADGEN_NODE: process.execPath,
    ...extra,
  };
}

/* -------------------------------------------------------------------------- */
/* Process costs                                                               */
/* -------------------------------------------------------------------------- */

async function timeExec(file, args, options) {
  const started = performance.now();
  let code = 0;
  let stdout;
  let stderr;
  try {
    ({ stdout, stderr } = await execFileAsync(file, args, { ...options, maxBuffer: 64 * 1024 * 1024 }));
  } catch (error) {
    code = typeof error.code === "number" ? error.code : 1;
    stdout = String(error.stdout ?? "");
    stderr = String(error.stderr ?? "");
  }
  return { ms: performance.now() - started, code, stdout, stderr };
}

async function repeat(times, run) {
  const samples = [];
  for (let index = 0; index < times; index += 1) {
    samples.push(await run(index));
  }
  return samples;
}

async function timeViewerLaunch(python, env, cwd) {
  const started = performance.now();
  const child = spawn(python, ["-m", "cadgen.viewer", "--api-only", "--host", "127.0.0.1", "--json"], {
    cwd,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const line = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error("viewer launch timed out")), 90_000);
    readline.createInterface({ input: child.stdout }).on("line", (text) => {
      if (text.trim().startsWith("{")) {
        clearTimeout(timer);
        resolve(JSON.parse(text));
      }
    });
    child.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`viewer exited ${code} before its JSON line`));
    });
  });
  const ms = performance.now() - started;
  // First request after the line: the contract says it answers at once.
  const requestStarted = performance.now();
  const response = await fetch(`${line.url.replace(/\/+$/, "")}/__cad/server`);
  await response.json();
  const firstRequestMs = performance.now() - requestStarted;
  child.kill("SIGTERM");
  await new Promise((resolve) => child.on("exit", resolve));
  return { ms, firstRequestMs, action: line.action };
}

async function daemonPid(python, env) {
  const { stdout } = await timeExec(
    python,
    ["-c", "import json; from cadgen.daemon import client; print(json.dumps(client.status()))"],
    { env },
  );
  try {
    return JSON.parse(stdout.trim().split("\n").at(-1))?.pid ?? null;
  } catch {
    return null;
  }
}

async function measureProcesses(options, scratch) {
  const python = resolvePython();
  const midModel = path.join(repoRoot, options.models[Math.min(1, options.models.length - 1)]);
  const socketEnv = daemonSocketEnv("processes");
  const freshStore = () => fs.mkdtempSync(path.join(scratch, "store-"));
  const baseEnv = cadgenEnv(socketEnv);
  const result = { python, imports: {}, viewer: {}, inspect: {} };

  const imports = {
    cadgen: "import cadgen",
    "cadgen.viewer": "import cadgen.viewer",
    "cadgen.daemon.client": "import cadgen.daemon.client",
    "build123d (a worker's warm import)": "import build123d",
  };
  for (const [name, code] of Object.entries(imports)) {
    const samples = await repeat(3, () => timeExec(python, ["-c", code], { env: baseEnv }));
    result.imports[name] = stats(samples.map((sample) => sample.ms));
    if (samples.some((sample) => sample.code !== 0)) {
      result.imports[name].error = samples.find((sample) => sample.code !== 0)?.stderr.trim().split("\n").at(-1);
    }
  }
  {
    const importtime = await timeExec(python, ["-X", "importtime", "-c", "import cadgen.viewer"], { env: baseEnv });
    result.imports.top = importtime.stderr
      .split("\n")
      .filter((line) => line.startsWith("import time:") && !line.includes("self [us]"))
      .map((line) => {
        const [, self, cumulative, name] = /import time:\s+(\d+)\s+\|\s+(\d+)\s+\|(.*)$/.exec(line) ?? [];
        return { name: String(name ?? "").trim(), depth: (name ?? "").length - (name ?? "").trimStart().length, selfMs: Number(self) / 1000, cumulativeMs: Number(cumulative) / 1000 };
      })
      .filter((entry) => entry.name && entry.depth <= 5)
      .sort((a, b) => b.cumulativeMs - a.cumulativeMs)
      .slice(0, 12);
  }

  {
    const cwd = fs.mkdtempSync(path.join(scratch, "served-"));
    const samples = await repeat(3, () => timeViewerLaunch(python, baseEnv, cwd));
    result.viewer = {
      launch: stats(samples.map((sample) => sample.ms)),
      firstRequest: stats(samples.map((sample) => sample.firstRequestMs)),
      actions: samples.map((sample) => sample.action),
    };
  }

  // Through `cadgen.cli` (the console script's entry): that is where the
  // daemon shim lives. `-m cadgen.cli.step_inspect` would run every job cold.
  const inspect = (env) => timeExec(python, ["-m", "cadgen.cli", "step", "inspect", "validate", midModel], { env, cwd: repoRoot });
  const storeA = freshStore();
  result.inspect["transient, store miss"] = await inspect({ ...baseEnv, CADGEN_DAEMON: "0", CADGEN_CACHE_DIR: storeA });
  result.inspect["transient, store hit"] = await inspect({ ...baseEnv, CADGEN_DAEMON: "0", CADGEN_CACHE_DIR: storeA });
  const storeB = freshStore();
  result.inspect["daemon first job (spawn), store miss"] = await inspect({ ...baseEnv, CADGEN_CACHE_DIR: storeB });
  result.inspect["daemon warm, store hit"] = await inspect({ ...baseEnv, CADGEN_CACHE_DIR: storeB });
  const storeC = freshStore();
  result.inspect["daemon warm, store miss"] = await inspect({ ...baseEnv, CADGEN_CACHE_DIR: storeC });
  result.inspect["daemon warm, store hit (2nd)"] = await inspect({ ...baseEnv, CADGEN_CACHE_DIR: storeC });
  // The compile itself — the job the viewer submits for a document whose
  // bytes have no tree — on the warm daemon, per model, store miss then hit.
  result.compile = {};
  for (const model of options.models) {
    const storeD = freshStore();
    const args = ["-m", "cadgen.cli", "step", "compile", path.join(repoRoot, model)];
    result.compile[`${path.basename(model)} — daemon warm, store miss`] = await timeExec(python, args, { env: { ...baseEnv, CADGEN_CACHE_DIR: storeD }, cwd: repoRoot });
    result.compile[`${path.basename(model)} — daemon warm, store hit`] = await timeExec(python, args, { env: { ...baseEnv, CADGEN_CACHE_DIR: storeD }, cwd: repoRoot });
  }
  for (const entry of [...Object.values(result.inspect), ...Object.values(result.compile)]) {
    entry.ms = round(entry.ms, 0);
    entry.stdout = entry.stdout.trim().split("\n").slice(-2).join(" | ");
    entry.stderr = entry.stderr.trim().split("\n").slice(-2).join(" | ");
  }

  const pid = await daemonPid(python, baseEnv);
  if (pid) {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      /* already gone */
    }
  }
  result.daemonPid = pid;
  return result;
}

/* -------------------------------------------------------------------------- */
/* The app timeline                                                            */
/* -------------------------------------------------------------------------- */

const PERF_NAMES = { tessellate: "cad:tessellate", hoverPick: "cad:hover-pick", frame: "cad:frame" };

async function launchApp(userData, cacheEnv) {
  const { CAD_DESKTOP_PYTHON: _unset, ...inherited } = process.env;
  const env = { ...inherited, NODE_ENV: "test", HARDCORE_NO_PLUGIN_INSTALL: "1", ...cacheEnv };
  const stdoutLines = [];
  const started = performance.now();
  const app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${userData}`],
    env,
  });
  const child = app.process();
  for (const stream of [child.stdout, child.stderr]) {
    if (stream) {
      readline.createInterface({ input: stream }).on("line", (line) => stdoutLines.push({ at: performance.now(), line }));
    }
  }
  const page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  const windowReadyMs = performance.now() - started;
  await page.evaluate(() => {
    globalThis.__cadgenPerf = true;
  });
  return { app, page, stdoutLines, windowReadyMs };
}

async function addProject(page) {
  await page.evaluate((root) => window.hardcore.projects.addPath({ path: root }), repoRoot);
  // The strip binds to the project asynchronously; `+` does nothing until it has.
  const newTab = page.getByRole("button", { name: "New tab", exact: true });
  await newTab.waitFor({ state: "visible", timeout: 30_000 });
  const deadline = performance.now() + 30_000;
  while (!(await newTab.isEnabled())) {
    if (performance.now() > deadline) {
      throw new Error("the explorer strip never bound to the project");
    }
    await page.waitForTimeout(50);
  }
  // The explorer starts closed and remembers a person's toggle per project
  // (localStorage), so a relaunch may find it open already.
  const explorerWidth = () => page.evaluate(() => document.querySelector("[data-testid=explorer]")?.getBoundingClientRect().width ?? 0);
  if ((await explorerWidth()) === 0) {
    await page.getByRole("button", { name: "Toggle explorer" }).click();
    await page.waitForFunction(() => {
      const explorer = document.querySelector("[data-testid=explorer]");
      return explorer ? explorer.getBoundingClientRect().width > 0 : false;
    }, null, { timeout: 15_000 });
  }
}

/** Every /__cad and /__tess_cache response the page (or its workers) makes, with the request's timing. */
function recordResponses(page, sink) {
  // `request.timing()` answers -1 for every field under Electron, so the
  // round trip is stamped here: issue on `request`, finish on `response`.
  const issued = new WeakMap();
  const interesting = (url) => /\/__cad\/|\/__tess_cache\//.test(url);
  page.on("request", (request) => {
    if (interesting(request.url())) {
      issued.set(request, performance.now());
    }
  });
  page.on("response", (response) => {
    const url = response.url();
    if (!interesting(url)) {
      return;
    }
    const request = response.request();
    const startedAt = issued.get(request) ?? null;
    const headers = response.headers();
    const at = performance.now();
    sink.push({
      at,
      startedAt,
      method: request.method(),
      url,
      status: response.status(),
      durationMs: startedAt === null ? null : at - startedAt,
      bytes: headers["content-length"] ? Number(headers["content-length"]) : null,
    });
  });
}

async function openFromTree(page, target) {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: "File" }).click();
  const filter = page.getByLabel("Filter files");
  await filter.fill(target);
  const option = page.getByRole("option", { name: target, exact: false }).first();
  await option.waitFor({ state: "visible", timeout: 30_000 });
  await option.click();
}

function pageMeasures(page, name) {
  return page.evaluate((measureName) => {
    return performance.getEntriesByName(measureName).map((entry) => ({
      start: entry.startTime,
      duration: entry.duration,
      detail: entry.detail ?? null,
    }));
  }, name);
}

function clearMeasures(page) {
  return page.evaluate(() => performance.clearMeasures());
}

async function pageNow(page) {
  return page.evaluate(() => performance.now());
}

async function waitForModel(page, deadlineMs) {
  const surface = page.locator("[data-cad-surface]");
  const canvas = surface.locator("canvas").first();
  const started = performance.now();
  await canvas.waitFor({ state: "visible", timeout: deadlineMs });
  const canvasAt = performance.now();
  // The loading overlay is `role=status` inside the surface; the model is
  // painted once it is gone. Poll rather than wait for it to appear: a warm
  // open may never show it.
  await page.waitForFunction(() => {
    const host = document.querySelector("[data-cad-surface]");
    if (!host || !host.querySelector("canvas")) {
      return false;
    }
    return !host.querySelector("[role=status]");
  }, null, { timeout: Math.max(1000, deadlineMs - (performance.now() - started)), polling: 25 });
  const paintedAt = performance.now();
  // The STEP sheet's tree, inside the surface — the explorer's file tree is a
  // `tree` too.
  await surface.locator("[role=tree]").first().waitFor({ state: "visible", timeout: Math.max(1000, deadlineMs - (performance.now() - started)) });
  const sheetAt = performance.now();
  return { canvasAt, paintedAt, sheetAt };
}

async function canvasBox(page) {
  const box = await page.locator("[data-cad-surface] canvas").first().boundingBox();
  if (!box) {
    throw new Error("no canvas to interact with");
  }
  return box;
}

async function sweepHover(page, box, durationMs) {
  const started = performance.now();
  let step = 0;
  while (performance.now() - started < durationMs) {
    const t = step / 40;
    const x = box.x + box.width * (0.5 + 0.4 * Math.sin(t));
    const y = box.y + box.height * (0.5 + 0.35 * Math.sin(2.3 * t + 1));
    await page.mouse.move(x, y);
    step += 1;
  }
  return step;
}

async function dragOrbit(page, box, durationMs) {
  const centerX = box.x + box.width / 2;
  const centerY = box.y + box.height / 2;
  await page.mouse.move(centerX, centerY);
  await page.mouse.down();
  const started = performance.now();
  let step = 0;
  while (performance.now() - started < durationMs) {
    const t = step / 30;
    await page.mouse.move(centerX + box.width * 0.25 * Math.cos(t), centerY + box.height * 0.2 * Math.sin(t));
    step += 1;
  }
  await page.mouse.up();
  return step;
}

/**
 * Open `model` from the tree and record the timeline. `phase` names the
 * expectation: cold, warm-session (tab switch) or warm-relaunch.
 */
async function timeOpen(context, model, phase, options) {
  const { page, stdoutLines, responses } = context;
  await clearMeasures(page);
  const responsesFrom = responses.length;
  const stdoutFrom = stdoutLines.length;
  const openedAt = performance.now();
  const pageOpenedAt = await pageNow(page);
  const toHarness = (pageTime) => openedAt + (pageTime - pageOpenedAt);

  if (phase === "warm-session") {
    await page.getByRole("tab", { name: path.basename(model) }).first().click();
  } else {
    await openFromTree(page, model);
  }
  const marks = await waitForModel(page, 240_000);
  const box = await canvasBox(page);

  // Time to interactive: the first hover pick after the pointer moves.
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.mouse.move(box.x + box.width * 0.52, box.y + box.height * 0.5);
  await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.52);
  await page.waitForFunction((name) => performance.getEntriesByName(name).length > 0, PERF_NAMES.hoverPick, { timeout: 30_000 }).catch(() => {});
  const firstPick = (await pageMeasures(page, PERF_NAMES.hoverPick))[0] ?? null;
  const frames = await pageMeasures(page, PERF_NAMES.frame);
  const tessellations = await pageMeasures(page, PERF_NAMES.tessellate);
  const firstFrame = frames[0] ?? null;
  const firstModelFrame = frames.find((entry) => toHarness(entry.start) >= marks.paintedAt - 100) ?? null;

  await clearMeasures(page);
  const hoverMoves = await sweepHover(page, box, options.hoverMs);
  const hoverPicks = await pageMeasures(page, PERF_NAMES.hoverPick);
  const hoverFrames = await pageMeasures(page, PERF_NAMES.frame);
  await clearMeasures(page);
  const orbitMoves = await dragOrbit(page, box, options.orbitMs);
  const orbitFrames = await pageMeasures(page, PERF_NAMES.frame);
  await clearMeasures(page);

  const viewerLine = stdoutLines.slice(stdoutFrom).find((entry) => /\[viewer\] (started|reused) /.test(entry.line));
  // A viewer that was up before the click: a pre-warm, or an earlier open.
  const viewerWarm = !viewerLine && stdoutLines.slice(0, stdoutFrom).some((entry) => /\[viewer\] (started|reused) /.test(entry.line));
  const own = responses.slice(responsesFrom);
  const compile = own.filter((entry) => entry.method === "POST" && entry.url.includes("/__cad/artifact"));
  const catalog = own.filter((entry) => entry.method === "GET" && entry.url.includes("/__cad/catalog"));
  const statusPolls = own.filter((entry) => entry.method === "GET" && entry.url.includes("/__cad/artifact"));
  const store = own.filter((entry) => entry.url.includes("/__cad/store") || entry.url.includes("/__cad/asset"));
  const tessGets = own.filter((entry) => entry.method === "GET" && entry.url.includes("/__tess_cache/"));
  const tessBatch = own.filter((entry) => entry.method === "POST" && entry.url.includes("/__tess_cache/batch"));
  const tessPuts = own.filter((entry) => entry.method === "POST" && entry.url.includes("/__tess_cache/") && !entry.url.includes("/batch"));

  const hits = tessellations.filter((entry) => entry.detail?.cacheHit);
  const misses = tessellations.filter((entry) => !entry.detail?.cacheHit);
  return {
    model,
    phase,
    ms: {
      viewerUp: viewerLine ? round(viewerLine.at - openedAt, 0) : null,
      viewerWarm,
      canvas: round(marks.canvasAt - openedAt, 0),
      firstFrame: firstFrame ? round(toHarness(firstFrame.start) - openedAt, 0) : null,
      compile: compile.length ? round(compile[0].durationMs, 0) : null,
      compileFinishedAt: compile.length ? round(compile[0].at - openedAt, 0) : null,
      modelPainted: round(marks.paintedAt - openedAt, 0),
      firstModelFrame: firstModelFrame ? round(toHarness(firstModelFrame.start + firstModelFrame.duration) - openedAt, 0) : null,
      sheetReady: round(marks.sheetAt - openedAt, 0),
      interactive: firstPick ? round(toHarness(firstPick.start + firstPick.duration) - openedAt, 0) : null,
      firstPickCost: firstPick ? round(firstPick.duration, 2) : null,
    },
    tessellation: {
      components: tessellations.length,
      hits: hits.length,
      misses: misses.length,
      hit: stats(hits.map((entry) => entry.duration)),
      miss: stats(misses.map((entry) => entry.duration)),
      wall: tessellations.length
        ? round(Math.max(...tessellations.map((entry) => entry.start + entry.duration)) - Math.min(...tessellations.map((entry) => entry.start)), 0)
        : null,
    },
    network: {
      catalog: { count: catalog.length, ms: stats(catalog.map((entry) => entry.durationMs)) },
      statusPolls: statusPolls.length,
      store: { count: store.length, bytes: store.reduce((sum, entry) => sum + (entry.bytes ?? 0), 0), ms: stats(store.map((entry) => entry.durationMs)) },
      tessCache: {
        gets: tessGets.length,
        getHits: tessGets.filter((entry) => entry.status === 200).length,
        batch: tessBatch.length,
        puts: tessPuts.length,
      },
    },
    hover: { moves: hoverMoves, picks: stats(hoverPicks.map((entry) => entry.duration)), frames: stats(hoverFrames.map((entry) => entry.duration)) },
    orbit: { moves: orbitMoves, frames: stats(orbitFrames.map((entry) => entry.duration)), fps: round(orbitFrames.length / (options.orbitMs / 1000), 1) },
    // The raw timeline, relative to the click: every backend round trip
    // (status polls collapsed to a count) and main's log lines.
    timeline: [
      ...own
        .filter((entry) => !(entry.method === "GET" && entry.url.includes("/__cad/artifact")))
        .filter((entry) => !(entry.url.includes("/__cad/store") || entry.url.includes("/__cad/asset")) || entry.url.includes("assembly.json"))
        .map((entry) => ({
          t: round((entry.startedAt ?? entry.at) - openedAt, 0),
          ms: round(entry.durationMs, 0),
          what: `${entry.method} ${entry.url.replace(/^https?:\/\/[^/]+/, "").replace(/([?&]file=)[^&]*/, (_, key) => `${key}…`)} ${entry.status}`,
        })),
      ...stdoutLines.slice(stdoutFrom).map((entry) => ({ t: round(entry.at - openedAt, 0), what: `main: ${entry.line.slice(0, 160)}` })),
    ].sort((a, b) => a.t - b.t),
  };
}

async function measureApp(options, scratch) {
  if (!fs.existsSync(path.join(appRoot, "out", "main", "index.js"))) {
    throw new Error("no build under out/: run `npm run build` first");
  }
  const userData = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-perf-"));
  const cacheDir = options.cacheDir ?? fs.mkdtempSync(path.join(scratch, "app-store-"));
  const cacheEnv = { CADGEN_CACHE_DIR: cacheDir, ...daemonSocketEnv("app") };
  const result = { userData, cacheDir, launches: [], opens: [] };
  const python = resolvePython();

  const session = async (label, body) => {
    const launched = await launchApp(userData, cacheEnv);
    const responses = [];
    recordResponses(launched.page, responses);
    const context = { ...launched, responses };
    const projectStarted = performance.now();
    await addProject(launched.page);
    result.launches.push({ label, windowReadyMs: round(launched.windowReadyMs, 0), projectReadyMs: round(performance.now() - projectStarted, 0) });
    try {
      await body(context);
    } finally {
      // What came up on its own after the project was added — the viewer
      // and the daemon a pre-warm starts — as ms from the add; null when
      // nothing did (the first click then asks for the viewer itself).
      const firstLine = (pattern) => launched.stdoutLines.find((entry) => pattern.test(entry.line));
      const viewerLine = firstLine(/\[viewer\] (started|reused) /);
      const daemonLine = firstLine(/\[daemon\] warming /);
      const launch = result.launches.at(-1);
      launch.viewerWarmMs = viewerLine ? round(viewerLine.at - projectStarted, 0) : null;
      launch.daemonWarmMs = daemonLine ? round(daemonLine.at - projectStarted, 0) : null;
      const closing = performance.now();
      await launched.app.close();
      launch.quitMs = round(performance.now() - closing, 0);
    }
  };

  await session("cold", async (context) => {
    for (const model of options.models) {
      process.stderr.write(`  cold  ${model}\n`);
      result.opens.push(await timeOpen(context, model, "cold", options));
    }
    // Warm in session: the tab is still there; switching back remounts the
    // surface over the renderer's memory caches.
    for (const model of options.models) {
      process.stderr.write(`  warm-session  ${model}\n`);
      result.opens.push(await timeOpen(context, model, "warm-session", options));
    }
    // The strip is restored on relaunch with its active tab; leave a
    // markdown file active so no model loads before the next timer starts.
    await openFromTree(context.page, "AGENTS.md");
    await context.page.locator("[data-cad-surface]").waitFor({ state: "detached", timeout: 15_000 });
  });

  await session("relaunch", async (context) => {
    for (const model of options.models) {
      process.stderr.write(`  warm-relaunch  ${model}\n`);
      result.opens.push(await timeOpen(context, model, "warm-relaunch", options));
    }
  });

  const pid = await daemonPid(python, cadgenEnv(cacheEnv));
  if (pid) {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      /* already gone */
    }
  }
  fs.rmSync(userData, { recursive: true, force: true });
  return result;
}

/* -------------------------------------------------------------------------- */
/* Report                                                                      */
/* -------------------------------------------------------------------------- */

function report(result) {
  const lines = [];
  if (result.processes) {
    const p = result.processes;
    lines.push(`## cadgen process costs (${p.python})`, "", "| Measurement | p50 | max |", "| --- | --- | --- |");
    for (const [name, entry] of Object.entries(p.imports)) {
      if (name === "top") {
        continue;
      }
      lines.push(`| \`${name}\` | ${fmt(entry.p50)} | ${fmt(entry.max)}${entry.error ? ` (${entry.error})` : ""} |`);
    }
    lines.push(`| viewer launch → JSON line | ${fmt(p.viewer.launch?.p50)} | ${fmt(p.viewer.launch?.max)} |`);
    lines.push(`| viewer first request after the line | ${fmt(p.viewer.firstRequest?.p50)} | ${fmt(p.viewer.firstRequest?.max)} |`);
    for (const [name, entry] of Object.entries(p.inspect)) {
      lines.push(`| \`step inspect validate\` — ${name} | ${fmt(entry.ms)} | exit ${entry.code} |`);
    }
    for (const [name, entry] of Object.entries(p.compile ?? {})) {
      lines.push(`| \`step compile\` — ${name} | ${fmt(entry.ms)} | exit ${entry.code} |`);
    }
    lines.push("", "Top-level imports by cumulative time (`-X importtime`, `import cadgen.viewer`):", "");
    for (const entry of p.imports.top ?? []) {
      lines.push(`- ${entry.name}: ${fmt(entry.cumulativeMs)}`);
    }
    lines.push("");
  }
  if (result.app) {
    const a = result.app;
    lines.push("## App launches", "", "| Launch | window ready | project ready | viewer up after add | daemon warming after add | quit |", "| --- | --- | --- | --- | --- | --- |");
    for (const launch of a.launches) {
      lines.push(`| ${launch.label} | ${fmt(launch.windowReadyMs)} | ${fmt(launch.projectReadyMs)} | ${fmt(launch.viewerWarmMs)} | ${fmt(launch.daemonWarmMs)} | ${fmt(launch.quitMs)} |`);
    }
    lines.push("", "## Opens (ms from the click in the tree)", "");
    lines.push("| Model | Phase | viewer up | canvas | first frame | compile | model painted | sheet | interactive | tess (n, hit/miss, wall) | store GETs | tess cache GET hit/total, PUT |");
    lines.push("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |");
    for (const open of a.opens) {
      const t = open.tessellation;
      lines.push(
        `| ${path.basename(open.model)} | ${open.phase} | ${open.ms.viewerWarm ? "warm" : fmt(open.ms.viewerUp)} | ${fmt(open.ms.canvas)} | ${fmt(open.ms.firstFrame)} | ${fmt(open.ms.compile)} | ${fmt(open.ms.modelPainted)} | ${fmt(open.ms.sheetReady)} | ${fmt(open.ms.interactive)} | ${t.components}, ${t.hits}/${t.misses}, ${fmt(t.wall)} | ${open.network.store.count} (${round(open.network.store.bytes / 1024, 0)} KB) | ${open.network.tessCache.getHits}/${open.network.tessCache.gets}+${open.network.tessCache.batch}b, ${open.network.tessCache.puts} |`,
      );
    }
    lines.push("", "## Interaction", "", "| Model | Phase | hover picks | hover frames | orbit frames | orbit fps |", "| --- | --- | --- | --- | --- | --- |");
    for (const open of a.opens) {
      lines.push(`| ${path.basename(open.model)} | ${open.phase} | ${fmtStats(open.hover.picks)} | ${fmtStats(open.hover.frames)} | ${fmtStats(open.orbit.frames)} | ${open.orbit.fps} |`);
    }
    lines.push("", "## Tessellation per component", "", "| Model | Phase | miss | hit |", "| --- | --- | --- | --- |");
    for (const open of a.opens) {
      lines.push(`| ${path.basename(open.model)} | ${open.phase} | ${fmtStats(open.tessellation.miss)} | ${fmtStats(open.tessellation.hit)} |`);
    }
    lines.push("", "## Timelines (cold and relaunch; t = ms from the click, ms = round trip)", "");
    for (const open of a.opens.filter((entry) => entry.phase !== "warm-session")) {
      lines.push(`### ${path.basename(open.model)} — ${open.phase}`, "");
      for (const item of open.timeline) {
        lines.push(`- ${String(item.t).padStart(6)}  ${item.ms !== undefined && item.ms !== null ? `(${item.ms} ms) ` : ""}${item.what}`);
      }
      lines.push("");
    }
  }
  return lines.join("\n");
}

/* -------------------------------------------------------------------------- */

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const scratch = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-perf-scratch-"));
  const result = { at: new Date().toISOString(), host: { platform: process.platform, arch: process.arch, cpus: os.cpus().length, model: os.cpus()[0]?.model, memoryGb: round(os.totalmem() / 2 ** 30, 0) }, options };
  try {
    if (options.processes) {
      process.stderr.write("process costs…\n");
      result.processes = await measureProcesses(options, scratch);
    }
    if (options.app) {
      process.stderr.write("app timeline…\n");
      result.app = await measureApp(options, scratch);
    }
  } finally {
    // The daemons' own job log — `<tool> [...] -> exit 0 in 2.57s (worker …)`
    // per job — before their directory goes.
    if (socketDir && fs.existsSync(socketDir)) {
      result.daemonLogs = Object.fromEntries(
        fs.readdirSync(socketDir).filter((name) => name.endsWith(".log")).map((name) => [name, fs.readFileSync(path.join(socketDir, name), "utf8").trim().split("\n")]),
      );
    }
    fs.mkdirSync(path.dirname(options.out), { recursive: true });
    fs.writeFileSync(options.out, JSON.stringify(result, null, 2));
    if (!options.cacheDir) {
      fs.rmSync(scratch, { recursive: true, force: true });
    }
    if (socketDir) {
      fs.rmSync(socketDir, { recursive: true, force: true });
    }
  }
  process.stdout.write(`${report(result)}\n\nraw: ${options.out}\n`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
