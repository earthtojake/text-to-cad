#!/usr/bin/env node
// Headless per-publish main-thread timing + orbit frame-time harness for the
// CAD Viewer (companion to measure.mjs). Loads ONE viewer file, records:
//   - window.__cadSceneSync entries: main-thread ms of every scene sync (the
//     effect that turns a published mesh state into display records), tagged
//     rebuild|reuse
//   - long tasks (PerformanceObserver) between the first and final publish
//   - time-to-loaded, GPU buffer count/bytes (bufferData instrumentation)
//   - a scripted orbit drag after load: frame time median/p90 and draw calls
//     per frame while the camera moves
// NEVER opens anything in the user's browser; requires a viewer the caller started.
//
// Usage: node publish-timing.mjs --url http://127.0.0.1:3420 \
//   --file assemblies/STEP/anthropomorphic_hand/routing_layout_review.step --label before [--out x.json]

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const PLAYWRIGHT_FROM = process.env.PLAYWRIGHT_FROM
  || "/Users/jakefitzgerald/robots/text-to-cad/apps/viewer/node_modules/playwright";
const require = createRequire(import.meta.url);
const { chromium } = require(PLAYWRIGHT_FROM);

const args = { url: "http://127.0.0.1:3420", file: "", label: "", timeoutMs: 600000, out: "", runs: 1, dragMs: 4000 };
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i += 1) {
  const flag = argv[i];
  if (flag === "--url") args.url = argv[++i];
  else if (flag === "--file") args.file = argv[++i];
  else if (flag === "--label") args.label = argv[++i];
  else if (flag === "--timeout-ms") args.timeoutMs = Number(argv[++i]);
  else if (flag === "--out") args.out = argv[++i];
  else if (flag === "--runs") args.runs = Number(argv[++i]);
  else if (flag === "--drag-ms") args.dragMs = Number(argv[++i]);
  else if (flag === "--screenshot") args.screenshot = argv[++i];
  else throw new Error(`unknown flag ${flag}`);
}
if (!args.file) throw new Error("--file is required");
if (!args.label) args.label = path.basename(args.file);

function initProbe() {
  const gpu = { liveBytes: 0, peakBytes: 0, liveBufferCount: 0, peakBufferCount: 0, uploads: 0, textureUploads: 0 };
  window.__gpuBufferStats = gpu;
  const sizes = new WeakMap();
  const bound = new Map();
  const draw = { total: 0, frames: [] };
  window.__drawStats = draw;
  for (const proto of [window.WebGLRenderingContext?.prototype, window.WebGL2RenderingContext?.prototype]) {
    if (!proto || proto.__patched) continue;
    proto.__patched = true;
    const { bindBuffer, bufferData, deleteBuffer } = proto;
    proto.bindBuffer = function (target, buffer) { bound.set(target, buffer); return bindBuffer.apply(this, arguments); };
    proto.bufferData = function (target, source) {
      const size = typeof source === "number" ? source : (source?.byteLength || 0);
      const buffer = bound.get(target);
      if (buffer) {
        const previous = sizes.get(buffer) || 0;
        if (previous === 0) { gpu.liveBufferCount += 1; gpu.peakBufferCount = Math.max(gpu.peakBufferCount, gpu.liveBufferCount); }
        sizes.set(buffer, size);
        gpu.liveBytes += size - previous;
        gpu.peakBytes = Math.max(gpu.peakBytes, gpu.liveBytes);
      }
      gpu.uploads += 1;
      return bufferData.apply(this, arguments);
    };
    proto.deleteBuffer = function (buffer) {
      const previous = sizes.get(buffer) || 0;
      if (previous > 0) { gpu.liveBytes -= previous; gpu.liveBufferCount -= 1; sizes.set(buffer, 0); }
      return deleteBuffer.apply(this, arguments);
    };
    for (const name of ["texImage2D", "texStorage2D", "texSubImage2D"]) {
      const original = proto[name];
      if (typeof original === "function") proto[name] = function () { gpu.textureUploads += 1; return original.apply(this, arguments); };
    }
    for (const name of ["drawElements", "drawArrays", "drawElementsInstanced", "drawArraysInstanced"]) {
      const original = proto[name];
      if (typeof original === "function") proto[name] = function () { draw.total += 1; return original.apply(this, arguments); };
    }
  }
  // Per-frame record: [t, frameMs, drawCalls]. Kept for the whole session; the
  // harness slices the drag window out of it.
  let last = performance.now();
  let base = 0;
  const onFrame = () => {
    const now = performance.now();
    draw.frames.push([Math.round(now), now - last, draw.total - base]);
    if (draw.frames.length > 20000) draw.frames.shift();
    base = draw.total;
    last = now;
    requestAnimationFrame(onFrame);
  };
  requestAnimationFrame(onFrame);
  window.__longTasks = [];
  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) window.__longTasks.push([Math.round(entry.startTime), Math.round(entry.duration)]);
    }).observe({ type: "longtask", buffered: true });
  } catch { /* unsupported */ }
  window.__meshCostRamp = [];
  let lastSeen = "";
  setInterval(() => {
    const cost = window.__cadMeshCost;
    if (!cost) return;
    const key = JSON.stringify(cost);
    if (key === lastSeen) return;
    lastSeen = key;
    window.__meshCostRamp.push({ atMs: Math.round(performance.now()), publishCount: cost.publishCount, loaded: cost.loadedComponents, final: cost.final });
  }, 50);
  window.__pageErrors = [];
  window.addEventListener("error", (event) => window.__pageErrors.push(String(event?.message || "")));
}

function percentile(values, p) {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * p))];
}

async function runOnce(run) {
  const targetUrl = `${args.url.replace(/\/+$/, "")}/?file=${encodeURIComponent(args.file)}`;
  const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "cad-viewer-timing-"));
  const browser = await chromium.launchPersistentContext(profileDir, {
    headless: true,
    viewport: { width: 1400, height: 900 },
    args: ["--use-angle=metal", "--enable-precise-memory-info", "--disable-features=PrivateNetworkAccessSendPreflights", "--disable-hang-monitor"]
  });
  const record = { run, label: args.label, file: args.file, loaded: false, crashed: false, timeToLoadedMs: null, sceneSync: null, longTasks: null, gpu: null, publishes: [], drag: null, renderMemoryProbe: null, errors: [] };
  try {
    const page = await browser.newPage();
    await page.addInitScript(initProbe);
    page.on("crash", () => { record.crashed = true; });
    page.on("pageerror", (error) => record.errors.push(String(error?.message || error).slice(0, 200)));
    page.on("console", (message) => {
      if (message.type() === "error" || message.type() === "warning") record.errors.push(`console.${message.type()}: ${message.text().slice(0, 400)}`);
    });
    const started = Date.now();
    await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
    const deadline = started + args.timeoutMs;
    while (Date.now() < deadline && !record.crashed) {
      const probe = await page.evaluate(() => ({
        modelKey: window.__cadModelPlacement?.modelKey || "",
        final: window.__cadMeshCost?.final === true
      }));
      if (probe.modelKey && probe.final) {
        record.loaded = true;
        record.timeToLoadedMs = Date.now() - started;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    if (!record.loaded) {
      record.errors.push(`timeout/crash before final publish (${args.timeoutMs} ms)`);
      return record;
    }
    // Let the final publish's scene sync and idle work (BVH builds) settle.
    await page.waitForTimeout(6000);
    const settled = await page.evaluate(() => ({
      sceneSync: window.__cadSceneSync ? JSON.parse(JSON.stringify(window.__cadSceneSync)) : null,
      longTasks: JSON.parse(JSON.stringify(window.__longTasks || [])),
      gpu: { ...window.__gpuBufferStats },
      publishes: JSON.parse(JSON.stringify(window.__meshCostRamp || [])),
      renderMemoryProbe: typeof window.__cadRenderMemoryProbe === "function" ? JSON.parse(JSON.stringify(window.__cadRenderMemoryProbe())) : null,
      inPageErrors: [...(window.__pageErrors || [])]
    }));
    Object.assign(record, settled);
    record.errors.push(...settled.inPageErrors.slice(0, 5));

    if (args.screenshot) {
      await page.screenshot({ path: args.screenshot.replace(/\.png$/, "") + `-${run}.png` });
    }
    // Scripted orbit drag across the viewport canvas.
    const canvas = page.locator("canvas").first();
    const box = await canvas.boundingBox();
    if (box) {
      const cx = box.x + box.width / 2;
      const cy = box.y + box.height / 2;
      const steps = Math.max(30, Math.round(args.dragMs / 16));
      const dragStart = await page.evaluate(() => performance.now());
      await page.mouse.move(cx - 200, cy);
      await page.mouse.down();
      for (let i = 1; i <= steps; i += 1) {
        const t = i / steps;
        await page.mouse.move(cx - 200 + 400 * t, cy + 80 * Math.sin(t * Math.PI * 2));
        await page.waitForTimeout(16);
      }
      await page.mouse.up();
      const dragEnd = await page.evaluate(() => performance.now());
      // 1 s more for damping frames to settle, then read frames within the drag window.
      await page.waitForTimeout(1000);
      const frames = await page.evaluate(([start, end]) => (
        window.__drawStats.frames.filter(([t]) => t >= start && t <= end)
      ), [dragStart, dragEnd]);
      const frameMs = frames.map((frame) => frame[1]);
      const drawCalls = frames.map((frame) => frame[2]).filter((count) => count > 0);
      record.drag = {
        durationMs: Math.round(dragEnd - dragStart),
        frames: frames.length,
        frameMsMedian: percentile(frameMs, 0.5),
        frameMsP90: percentile(frameMs, 0.9),
        frameMsMax: frameMs.length ? Math.max(...frameMs) : null,
        drawCallsPerFrameMedian: percentile(drawCalls, 0.5),
        drawCallsPerFrameMax: drawCalls.length ? Math.max(...drawCalls) : null
      };
    }
  } finally {
    await browser.close().catch(() => {});
    fs.rmSync(profileDir, { recursive: true, force: true });
  }
  return record;
}

const results = [];
for (let run = 1; run <= args.runs; run += 1) {
  const record = await runOnce(run);
  results.push(record);
  const entries = record.sceneSync?.entries || [];
  const byMode = {};
  for (const entry of entries) {
    byMode[entry.mode] = byMode[entry.mode] || { count: 0, totalMs: 0, maxMs: 0 };
    byMode[entry.mode].count += 1;
    byMode[entry.mode].totalMs += entry.ms;
    byMode[entry.mode].maxMs = Math.max(byMode[entry.mode].maxMs, entry.ms);
  }
  const firstPublish = record.publishes[0]?.atMs ?? null;
  const finalPublish = record.publishes.find((publish) => publish.final)?.atMs ?? null;
  const longTaskMs = (record.longTasks || [])
    .filter(([start]) => firstPublish !== null && start >= firstPublish - 50 && (finalPublish === null || start <= finalPublish + 15000))
    .reduce((sum, [, duration]) => sum + duration, 0);
  process.stderr.write([
    `=== ${record.label} run ${run} ===`,
    `  loaded=${record.loaded} ttloaded=${record.timeToLoadedMs} ms publishes=${record.publishes.length} first=${firstPublish} final=${finalPublish}`,
    `  scene syncs: ${entries.length} total=${Math.round(record.sceneSync?.totalMs || 0)} ms ${JSON.stringify(byMode)}`,
    `  per-sync ms: ${entries.map((entry) => `${entry.mode[0]}${entry.ms}(${entry.records})`).join(" ")}`,
    `  long tasks from first publish: ${longTaskMs} ms over ${(record.longTasks || []).length} tasks`,
    `  gpu: buffers=${record.gpu?.liveBufferCount} live=${((record.gpu?.liveBytes || 0) / 1048576).toFixed(1)} MiB peak=${((record.gpu?.peakBytes || 0) / 1048576).toFixed(1)} MiB uploads=${record.gpu?.uploads} tex=${record.gpu?.textureUploads}`,
    `  renderMemoryProbe: ${JSON.stringify(record.renderMemoryProbe)}`,
    `  drag: ${JSON.stringify(record.drag)}`,
    record.errors.length ? `  errors: ${record.errors.slice(0, 3).join(" ;; ")}` : ""
  ].filter(Boolean).join("\n") + "\n");
}
const payload = { args, results, generatedAt: new Date().toISOString() };
if (args.out) fs.writeFileSync(args.out, `${JSON.stringify(payload, null, 2)}\n`);
