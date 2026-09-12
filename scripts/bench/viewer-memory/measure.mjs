#!/usr/bin/env node
// Headless memory-measurement harness for the CAD Viewer (design/viewer-memory.md §7).
//
// Loads ONE viewer file in a headless Chromium and reports, per run:
//   - performance.memory (usedJSHeapSize / totalJSHeapSize), peak-sampled in-page
//   - GPU buffer bytes, instrumented from outside the client by wrapping
//     WebGL(2)RenderingContext bufferData/bindBuffer/deleteBuffer (the client
//     exposes no renderer handle, so renderer.info.memory is unreachable; this
//     measures the same thing three.js would report, plus a peak)
//   - Chromium renderer-process RSS (peak), sampled from Node via `ps`, which
//     survives a tab crash and includes worker heaps (same renderer process)
//   - time-to-first-paint (paint timeline) and time-to-loaded
//     (window.__cadModelPlacement.modelKey, the client's only render seam)
//   - crash / pageerror / RangeError capture, with how far the load got
//
// NEVER opens anything in the user's browser. Requires a viewer the caller
// started; it neither starts nor stops one.
//
// Usage:
//   node measure.mjs --url http://127.0.0.1:3390 \
//     --file assemblies/STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step \
//     --label r13 --runs 2 --timeout-ms 900000 [--out results.json] [--no-lod]

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const PLAYWRIGHT_FROM = process.env.PLAYWRIGHT_FROM
  || "/Users/jakefitzgerald/robots/text-to-cad/apps/viewer/node_modules/playwright";
const require = createRequire(import.meta.url);
const { chromium } = require(PLAYWRIGHT_FROM);

function parseArgs(argv) {
  const args = {
    url: "http://127.0.0.1:3390",
    file: "",
    label: "",
    runs: 2,
    timeoutMs: 900000,
    out: "",
    lod: true,
    sampleMs: 500
  };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === "--url") args.url = argv[++i];
    else if (flag === "--file") args.file = argv[++i];
    else if (flag === "--label") args.label = argv[++i];
    else if (flag === "--runs") args.runs = Number(argv[++i]);
    else if (flag === "--timeout-ms") args.timeoutMs = Number(argv[++i]);
    else if (flag === "--out") args.out = argv[++i];
    else if (flag === "--sample-ms") args.sampleMs = Number(argv[++i]);
    else if (flag === "--no-lod") args.lod = false;
    else throw new Error(`unknown flag ${flag}`);
  }
  if (!args.file) throw new Error("--file <root-relative path> is required");
  if (!args.label) args.label = path.basename(args.file);
  return args;
}

const args = parseArgs(process.argv.slice(2));
const mib = (bytes) => (Number(bytes) || 0) / (1024 * 1024);
const fmt = (bytes) => `${mib(bytes).toFixed(1)} MiB`;

// ---------------------------------------------------------------- in-page probe
// Injected before any client code runs. Two jobs: instrument the WebGL buffer
// uploads (the GPU mirror of the CPU typed arrays) and peak-sample the JS heap.
function initProbe() {
  const stats = {
    liveBytes: 0,
    peakBytes: 0,
    uploadCount: 0,
    liveBufferCount: 0,
    peakBufferCount: 0,
    textureUploads: 0,
    contexts: 0
  };
  const sizes = new WeakMap();
  const boundByTarget = new Map();
  window.__gpuBufferStats = stats;

  const patch = (proto) => {
    if (!proto || proto.__cadMemPatched) return;
    proto.__cadMemPatched = true;
    const bindBuffer = proto.bindBuffer;
    const bufferData = proto.bufferData;
    const deleteBuffer = proto.deleteBuffer;
    proto.bindBuffer = function (target, buffer) {
      boundByTarget.set(target, buffer);
      return bindBuffer.apply(this, arguments);
    };
    proto.bufferData = function (target, source) {
      const size = typeof source === "number"
        ? source
        : (source && (source.byteLength || 0)) || 0;
      const buffer = boundByTarget.get(target);
      if (buffer) {
        const previous = sizes.get(buffer) || 0;
        if (previous === 0) {
          stats.liveBufferCount += 1;
          if (stats.liveBufferCount > stats.peakBufferCount) {
            stats.peakBufferCount = stats.liveBufferCount;
          }
        }
        sizes.set(buffer, size);
        stats.liveBytes += size - previous;
        if (stats.liveBytes > stats.peakBytes) stats.peakBytes = stats.liveBytes;
      }
      stats.uploadCount += 1;
      return bufferData.apply(this, arguments);
    };
    proto.deleteBuffer = function (buffer) {
      const previous = sizes.get(buffer) || 0;
      if (previous > 0) {
        stats.liveBytes -= previous;
        stats.liveBufferCount -= 1;
        sizes.set(buffer, 0);
      }
      return deleteBuffer.apply(this, arguments);
    };
    for (const name of ["texImage2D", "texStorage2D", "compressedTexImage2D"]) {
      const original = proto[name];
      if (typeof original !== "function") continue;
      proto[name] = function () {
        stats.textureUploads += 1;
        return original.apply(this, arguments);
      };
    }
  };
  patch(window.WebGLRenderingContext && window.WebGLRenderingContext.prototype);
  patch(window.WebGL2RenderingContext && window.WebGL2RenderingContext.prototype);

  const getContext = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (kind, ...rest) {
    const context = getContext.call(this, kind, ...rest);
    if (context && /webgl/i.test(String(kind))) stats.contexts += 1;
    return context;
  };

  // JS heap peak. --enable-precise-memory-info makes these unquantized.
  const heap = { samples: 0, peakUsed: 0, peakTotal: 0, lastUsed: 0, lastTotal: 0 };
  window.__heapStats = heap;
  const sample = () => {
    const memory = performance.memory;
    if (!memory) return;
    heap.samples += 1;
    heap.lastUsed = memory.usedJSHeapSize;
    heap.lastTotal = memory.totalJSHeapSize;
    if (heap.lastUsed > heap.peakUsed) heap.peakUsed = heap.lastUsed;
    if (heap.lastTotal > heap.peakTotal) heap.peakTotal = heap.lastTotal;
  };
  sample();
  setInterval(sample, 250);

  // Allocation failures are the reported symptom (BUGS 032: RangeError while
  // copying attributes). Record them even when the client swallows them.
  window.__cadMemErrors = [];
  window.addEventListener("error", (event) => {
    window.__cadMemErrors.push(String(event?.message || event?.error || ""));
  });
  window.addEventListener("unhandledrejection", (event) => {
    window.__cadMemErrors.push(`unhandledrejection: ${String(event?.reason || "")}`);
  });

  // Draw calls and frame time. Lever B draws 2-3 line segments per occurrence,
  // so the per-frame draw-call count is the cheapest way to see that cost.
  const draw = { total: 0, lastFrame: 0, peakFrame: 0, frames: 0, lastFrameMs: 0, medianFrameMs: 0 };
  window.__drawStats = draw;
  for (const proto of [window.WebGLRenderingContext?.prototype, window.WebGL2RenderingContext?.prototype]) {
    for (const name of ["drawElements", "drawArrays", "drawElementsInstanced", "drawArraysInstanced"]) {
      const original = proto?.[name];
      if (typeof original !== "function") continue;
      proto[name] = function () { draw.total += 1; return original.apply(this, arguments); };
    }
  }
  // "First geometry on screen": the first rAF frame that actually ISSUED draw
  // calls after the first __cadMeshCost publish carrying components. Measured
  // from performance.now()'s time origin, i.e. navigation start.
  const paint = { firstGeometryPublishMs: null, firstGeometryFrameMs: null };
  window.__firstGeometry = paint;

  const frameTimes = [];
  let frameStart = performance.now();
  let frameBase = 0;
  const onFrame = () => {
    const now = performance.now();
    const cost = window.__cadMeshCost;
    if (paint.firstGeometryPublishMs === null && Number(cost?.componentCount) > 0) {
      paint.firstGeometryPublishMs = Math.round(now);
    }
    if (paint.firstGeometryFrameMs === null
      && paint.firstGeometryPublishMs !== null
      && draw.total - frameBase > 10) {
      paint.firstGeometryFrameMs = Math.round(now);
    }
    draw.lastFrame = draw.total - frameBase;
    if (draw.lastFrame > draw.peakFrame) draw.peakFrame = draw.lastFrame;
    frameBase = draw.total;
    draw.lastFrameMs = now - frameStart;
    frameStart = now;
    draw.frames += 1;
    if (draw.frames > 5) {
      frameTimes.push(draw.lastFrameMs);
      if (frameTimes.length > 240) frameTimes.shift();
      const sorted = [...frameTimes].sort((a, b) => a - b);
      draw.medianFrameMs = sorted[Math.floor(sorted.length / 2)];
    }
    requestAnimationFrame(onFrame);
  };
  requestAnimationFrame(onFrame);

  // Lever C ramp: the new client sets window.__cadMeshCost on every publish.
  // Record each distinct value with the time it appeared.
  window.__meshCostRamp = [];
  let lastSeen = "";
  setInterval(() => {
    const cost = window.__cadMeshCost;
    if (!cost) return;
    const key = JSON.stringify(cost);
    if (key === lastSeen) return;
    lastSeen = key;
    window.__meshCostRamp.push({ atMs: Math.round(performance.now()), cost });
  }, 100);

  // Progress: the LOD scheduler's only public event; also the client's stage text.
  window.__lodEvents = [];
  window.addEventListener("cad:lod-level", (event) => window.__lodEvents.push(event.detail));
}

// -------------------------------------------------------------- process sampler
// Peak RSS per Chromium process type, filtered to OUR browser by its unique
// playwright profile directory. Survives a renderer crash.
function sampleProcesses(profileDir) {
  let out = "";
  try {
    // -ww: macOS `ps` truncates args to terminal width otherwise, and the
    // profile-directory flag is how our browser is identified.
    out = execFileSync("/bin/ps", ["-axww", "-o", "pid=,ppid=,rss=,args="], {
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024
    });
  } catch {
    return null;
  }
  const rows = [];
  for (const line of out.split("\n")) {
    const match = line.match(/^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.*)$/);
    if (!match) continue;
    rows.push({ pid: Number(match[1]), ppid: Number(match[2]), rssBytes: Number(match[3]) * 1024, cmd: match[4] });
  }
  // The browser process carries --user-data-dir=<profileDir>; its children
  // (renderer, gpu-process, utility) may not, so walk the pid tree from it.
  const roots = rows.filter((row) => row.cmd.includes(profileDir)).map((row) => row.pid);
  if (!roots.length) return null;
  const ours = new Set(roots);
  let grew = true;
  while (grew) {
    grew = false;
    for (const row of rows) {
      if (!ours.has(row.pid) && ours.has(row.ppid)) { ours.add(row.pid); grew = true; }
    }
  }
  const byType = {};
  for (const row of rows) {
    if (!ours.has(row.pid)) continue;
    const typeMatch = row.cmd.match(/--type=([a-zA-Z-]+)/);
    const type = typeMatch ? typeMatch[1] : "browser";
    byType[type] = byType[type] || { rssBytes: 0, largestPidBytes: 0, pids: new Set() };
    byType[type].rssBytes += row.rssBytes;
    // A tab dies on ITS OWN process footprint, so the number the memory gate
    // is about is the largest single process of a type, not the type's sum.
    // Chromium runs more than one renderer here (the page plus its own
    // about:blank), and summing them reported a peak the page never reached.
    byType[type].largestPidBytes = Math.max(byType[type].largestPidBytes, row.rssBytes);
    byType[type].pids.add(row.pid);
  }
  const result = { all: { rssBytes: 0, largestPidBytes: 0, processCount: ours.size } };
  for (const [type, value] of Object.entries(byType)) {
    result[type] = {
      rssBytes: value.rssBytes,
      largestPidBytes: value.largestPidBytes,
      processCount: value.pids.size
    };
    result.all.rssBytes += value.rssBytes;
    result.all.largestPidBytes = Math.max(result.all.largestPidBytes, value.largestPidBytes);
  }
  return result;
}

function mergePeak(peak, sample) {
  if (!sample) return peak;
  for (const [type, value] of Object.entries(sample)) {
    const current = peak[type] || { rssBytes: 0, processCount: 0 };
    peak[type] = {
      rssBytes: Math.max(current.rssBytes, value.rssBytes),
      largestPidBytes: Math.max(current.largestPidBytes || 0, value.largestPidBytes || 0),
      processCount: Math.max(current.processCount, value.processCount)
    };
  }
  return peak;
}

// ------------------------------------------------------------------------- run
async function runOnce(runIndex) {
  const targetUrl = `${args.url.replace(/\/+$/, "")}/?file=${encodeURIComponent(args.file)}`;
  // A persistent context with OUR OWN profile directory: the directory is the
  // discriminator that ties `ps` rows to this browser (playwright's Browser
  // object exposes no pid).
  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "cad-viewer-memory-"));
  const browser = await chromium.launchPersistentContext(profileDir, {
    headless: true,
    viewport: { width: 1400, height: 900 },
    args: [
      // Real GPU on macOS; headless Chromium otherwise falls back to SwiftShader
      // (software WebGL), which changes both timings and driver-side memory.
      "--use-angle=metal",
      // Unquantized performance.memory.
      "--enable-precise-memory-info",
      // Same PNA relaxation the repo's other e2e harnesses use for loopback assets.
      "--disable-features=PrivateNetworkAccessSendPreflights",
      // Report the OOM instead of silently reloading the tab.
      "--disable-hang-monitor"
    ]
  });
  const record = {
    run: runIndex,
    label: args.label,
    file: args.file,
    url: targetUrl,
    lod: args.lod,
    crashed: false,
    crashMessage: "",
    loaded: false,
    timeToFirstPaintMs: null,
    timeToLoadedMs: null,
    heap: null,
    gpu: null,
    peakRss: {},
    lastStageText: "",
    lodEventCount: null,
    timeToFirstPublishMs: null,
    firstGeometryPublishMs: null,
    firstGeometryFrameMs: null,
    renderMemoryProbe: null,
    meshCost: null,
    meshCostRamp: [],
    draw: null,
    pageErrors: [],
    inPageErrors: []
  };
  const peakRss = record.peakRss;
  let sampler = null;
  try {
    const page = await browser.newPage();
    await page.addInitScript(initProbe);
    if (!args.lod) await page.addInitScript(() => { window.__CAD_VIEWER_LOD__ = false; });
    page.on("crash", () => { record.crashed = true; record.crashMessage = "page crash (renderer gone)"; });
    page.on("pageerror", (error) => { record.pageErrors.push(String(error?.message || error)); });
    page.on("console", (message) => {
      if (message.type() === "error") record.pageErrors.push(`console: ${message.text().slice(0, 300)}`);
    });

    sampler = setInterval(() => { mergePeak(peakRss, sampleProcesses(profileDir)); }, args.sampleMs);

    const started = Date.now();
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 120000 });

    // Poll the client's render seam (window.__cadModelPlacement.modelKey) rather
    // than a fixed settle: the full hand can tessellate for minutes.
    const deadline = started + args.timeoutMs;
    let stage = "";
    while (Date.now() < deadline && !record.crashed) {
      let probe = null;
      try {
        probe = await page.evaluate(() => ({
          modelKey: (window.__cadModelPlacement && window.__cadModelPlacement.modelKey) || "",
          stage: (document.body?.innerText || "").split("\n").filter((line) =>
            /loading|building|componen|compil|render/i.test(line)).slice(0, 3).join(" | "),
          heap: window.__heapStats ? { ...window.__heapStats } : null,
          gpu: window.__gpuBufferStats ? { ...window.__gpuBufferStats } : null,
          errors: [...(window.__cadMemErrors || [])],
          lodEvents: (window.__lodEvents || []).length,
          meshCost: window.__cadMeshCost ? JSON.parse(JSON.stringify(window.__cadMeshCost)) : null,
          rampLength: (window.__meshCostRamp || []).length,
          draw: window.__drawStats ? { ...window.__drawStats } : null,
          firstGeometry: window.__firstGeometry ? { ...window.__firstGeometry } : null,
          paint: performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime])
        }));
      } catch (error) {
        const message = String(error?.message || error);
        if (/crash|Target closed|Execution context was destroyed|detached/i.test(message)) {
          record.crashed = true;
          record.crashMessage = message.split("\n")[0];
          break;
        }
        throw error;
      }
      if (probe.heap) record.heap = probe.heap;
      if (probe.gpu) record.gpu = probe.gpu;
      if (probe.errors?.length) record.inPageErrors = probe.errors;
      if (probe.meshCost) {
        record.meshCost = probe.meshCost;
        if (record.timeToFirstPublishMs === null) record.timeToFirstPublishMs = Date.now() - started;
      }
      if (probe.draw) record.draw = probe.draw;
      if (probe.firstGeometry) {
        record.firstGeometryPublishMs = probe.firstGeometry.firstGeometryPublishMs;
        record.firstGeometryFrameMs = probe.firstGeometry.firstGeometryFrameMs;
      }
      record.lodEventCount = probe.lodEvents;
      if (probe.stage) { stage = probe.stage; record.lastStageText = stage; }
      if (record.timeToFirstPaintMs === null) {
        const first = (probe.paint || []).find(([name]) => name === "first-contentful-paint")
          || (probe.paint || [])[0];
        if (first) record.timeToFirstPaintMs = Math.round(first[1]);
      }
      // Lever C publishes partial geometry, and __cadModelPlacement appears on
      // the FIRST publish. "loaded" must therefore mean the LAST publish:
      // meshCost.final (new client) or simply modelKey (old client, one publish).
      const fullyPublished = probe.meshCost
        ? (probe.meshCost.final === true
          || (Number(probe.meshCost.loadedComponents) > 0
            && Number(probe.meshCost.loadedComponents) === Number(probe.meshCost.totalComponents)))
        : true;
      if (probe.modelKey && fullyPublished) {
        record.loaded = true;
        record.timeToLoadedMs = Date.now() - started;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!record.loaded && !record.crashed) {
      record.crashMessage = `timeout after ${args.timeoutMs} ms (stage: ${stage || "unknown"})`;
    }
    if (record.loaded) {
      // Let the first frames render, then take the settled reading.
      await new Promise((resolve) => setTimeout(resolve, 5000));
      try {
        const settled = await page.evaluate(() => ({
          heap: { ...window.__heapStats },
          gpu: { ...window.__gpuBufferStats },
          lodEvents: (window.__lodEvents || []).length,
          meshCost: window.__cadMeshCost ? JSON.parse(JSON.stringify(window.__cadMeshCost)) : null,
          ramp: JSON.parse(JSON.stringify(window.__meshCostRamp || [])),
          draw: { ...window.__drawStats },
          firstGeometry: { ...(window.__firstGeometry || {}) },
          // New client's own accounting seam: surface/edge/BVH GPU-array bytes
          // and render-asset cache stats.
          renderMemoryProbe: typeof window.__cadRenderMemoryProbe === "function"
            ? JSON.parse(JSON.stringify(window.__cadRenderMemoryProbe()))
            : null
        }));
        record.heap = settled.heap;
        record.gpu = settled.gpu;
        record.lodEventCount = settled.lodEvents;
        if (settled.meshCost) record.meshCost = settled.meshCost;
        record.meshCostRamp = settled.ramp || [];
        record.draw = settled.draw;
        record.renderMemoryProbe = settled.renderMemoryProbe;
        if (settled.firstGeometry) {
          record.firstGeometryPublishMs = settled.firstGeometry.firstGeometryPublishMs;
          record.firstGeometryFrameMs = settled.firstGeometry.firstGeometryFrameMs;
        }
      } catch { /* a crash during settle is already recorded by the handler */ }
      // Separate garbage from retention. The peak is what decides whether the
      // tab survives, but a peak made of uncollected churn is fixed by
      // allocating less per publish, while a peak made of retained bytes is
      // fixed by holding less — different work. A forced collection, then a
      // settle for the worker isolates and the allocator to give memory back,
      // reads the second number.
      try {
        const cdp = await page.context().newCDPSession(page);
        await cdp.send("HeapProfiler.enable").catch(() => {});
        await cdp.send("HeapProfiler.collectGarbage");
        await cdp.detach().catch(() => {});
        await new Promise((resolve) => setTimeout(resolve, 5000));
        record.afterGc = {
          rss: sampleProcesses(profileDir),
          heapUsed: await page.evaluate(
            () => (performance.memory ? performance.memory.usedJSHeapSize : 0)
          ).catch(() => 0)
        };
      } catch { /* no CDP: the after-GC reading is simply absent */ }
    }
    mergePeak(peakRss, sampleProcesses(profileDir));
  } finally {
    if (sampler) clearInterval(sampler);
    await browser.close().catch(() => {});
    fs.rmSync(profileDir, { recursive: true, force: true });
  }
  return record;
}

const results = [];
for (let run = 1; run <= args.runs; run += 1) {
  process.stderr.write(`\n=== ${args.label} run ${run}/${args.runs} ===\n`);
  const record = await runOnce(run);
  results.push(record);
  const renderer = record.peakRss.renderer?.rssBytes || 0;
  const gpuProcess = record.peakRss["gpu-process"]?.rssBytes || 0;
  process.stderr.write([
    `  loaded=${record.loaded} crashed=${record.crashed}${record.crashMessage ? ` (${record.crashMessage})` : ""}`,
    `  ttfp=${record.timeToFirstPaintMs ?? "n/a"} ms  ttloaded=${record.timeToLoadedMs ?? "n/a"} ms`,
    `  heap used peak=${fmt(record.heap?.peakUsed)} total peak=${fmt(record.heap?.peakTotal)}`,
    `  gpu buffers peak=${fmt(record.gpu?.peakBytes)} live=${fmt(record.gpu?.liveBytes)} count=${record.gpu?.peakBufferCount ?? "n/a"} uploads=${record.gpu?.uploadCount ?? "n/a"}`,
    `  peak RSS renderer=${fmt(renderer)} (largest single renderer ${fmt(record.peakRss.renderer?.largestPidBytes)}) `
      + `gpu-process=${fmt(gpuProcess)} all-processes=${fmt(record.peakRss.all?.rssBytes)}`,
    record.afterGc
      ? `  after GC   renderer=${fmt(record.afterGc.rss.renderer?.rssBytes)} (largest ${fmt(record.afterGc.rss.renderer?.largestPidBytes)}) gpu-process=${fmt(record.afterGc.rss["gpu-process"]?.rssBytes)} all=${fmt(record.afterGc.rss.all?.rssBytes)} heap=${fmt(record.afterGc.heapUsed)}`
      : "  after GC   (not read)",
    `  lod events=${record.lodEventCount ?? "n/a"} stage="${record.lastStageText}"`,
    `  first publish=${record.timeToFirstPublishMs ?? "n/a"} ms  publishes=${record.meshCostRamp.length}  meshCost=${record.meshCost ? JSON.stringify(record.meshCost) : "ABSENT (old client)"}`,
    record.meshCostRamp.length
      ? `  ramp: ${record.meshCostRamp.slice(0, 4).map((step) => `${step.atMs}ms:${JSON.stringify(step.cost).slice(0, 110)}`).join("  ")}${record.meshCostRamp.length > 4 ? ` ... (+${record.meshCostRamp.length - 4})` : ""}`
      : "",
    `  first geometry: publish=${record.firstGeometryPublishMs ?? "n/a"} ms  ON SCREEN=${record.firstGeometryFrameMs ?? "n/a"} ms (from navigation start)`,
    `  renderMemoryProbe=${record.renderMemoryProbe ? JSON.stringify(record.renderMemoryProbe) : "ABSENT"}`,
    `  draw calls total=${record.draw?.total ?? "n/a"} per-frame last=${record.draw?.lastFrame ?? "n/a"} peak=${record.draw?.peakFrame ?? "n/a"} median frame=${record.draw?.medianFrameMs?.toFixed?.(1) ?? "n/a"} ms`,
    record.inPageErrors.length ? `  in-page errors: ${record.inPageErrors.slice(0, 3).join(" ;; ")}` : "",
    record.pageErrors.length ? `  page errors: ${record.pageErrors.slice(0, 3).join(" ;; ")}` : ""
  ].filter(Boolean).join("\n") + "\n");
}

const payload = { args, results, generatedAt: new Date().toISOString() };
if (args.out) {
  fs.writeFileSync(args.out, `${JSON.stringify(payload, null, 2)}\n`);
  process.stderr.write(`\nwrote ${args.out}\n`);
}
process.stdout.write(`${JSON.stringify(payload)}\n`);
