#!/usr/bin/env node
// 250 ms transient-peak profiler for one CAD Viewer load.
//
// Answers "what was the true peak and what was the loader doing then": samples
// process RSS per Chromium process type (Node side, via `ps` — survives a tab
// crash and never waits on a blocked main thread), renderer thread count
// (dedicated workers are THREADS inside the renderer on Chromium, not separate
// processes), CDP JS heap (also independent of the main thread), and the
// client's own loader state. Also samples macOS memory pressure and swap.
//
// Usage:
//   node profile.mjs --url http://127.0.0.1:3430 --file <root-relative> --out r13-profile.json

import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const PLAYWRIGHT_FROM = process.env.PLAYWRIGHT_FROM
  || "/Users/jakefitzgerald/robots/text-to-cad/apps/viewer/node_modules/playwright";
const require = createRequire(import.meta.url);
const { chromium } = require(PLAYWRIGHT_FROM);

const args = { url: "", file: "", out: "", timeoutMs: 1200000, sampleMs: 250 };
for (let i = 2; i < process.argv.length; i += 1) {
  const flag = process.argv[i];
  if (flag === "--url") args.url = process.argv[++i];
  else if (flag === "--file") args.file = process.argv[++i];
  else if (flag === "--out") args.out = process.argv[++i];
  else if (flag === "--timeout-ms") args.timeoutMs = Number(process.argv[++i]);
  else if (flag === "--sample-ms") args.sampleMs = Number(process.argv[++i]);
  else throw new Error(`unknown flag ${flag}`);
}
const mib = (bytes) => (Number(bytes) || 0) / (1024 * 1024);
const fmt = (bytes) => `${mib(bytes).toFixed(0)} MiB`;

function threadCount(pid) {
  try {
    const out = execFileSync("/bin/ps", ["-M", "-p", String(pid)], { encoding: "utf8" });
    return Math.max(0, out.trim().split("\n").length - 1);
  } catch { return 0; }
}

function psSample(profileDir) {
  let out = "";
  try {
    // macOS `ps` has no thcount keyword; threads come from `ps -M` below.
    out = execFileSync("/bin/ps", ["-axww", "-o", "pid=,ppid=,rss=,args="], {
      encoding: "utf8",
      maxBuffer: 64 * 1024 * 1024
    });
  } catch { return null; }
  const rows = [];
  for (const line of out.split("\n")) {
    const match = line.match(/^\s*(\d+)\s+(\d+)\s+(\d+)\s+(.*)$/);
    if (!match) continue;
    rows.push({
      pid: Number(match[1]), ppid: Number(match[2]),
      rssBytes: Number(match[3]) * 1024, cmd: match[4]
    });
  }
  const ours = new Set(rows.filter((row) => row.cmd.includes(profileDir)).map((row) => row.pid));
  if (!ours.size) return null;
  let grew = true;
  while (grew) {
    grew = false;
    for (const row of rows) {
      if (!ours.has(row.pid) && ours.has(row.ppid)) { ours.add(row.pid); grew = true; }
    }
  }
  const sample = { all: 0, browser: 0, renderer: 0, gpu: 0, utility: 0, other: 0, rendererThreads: 0, rendererCount: 0, processCount: 0 };
  for (const row of rows) {
    if (!ours.has(row.pid)) continue;
    sample.processCount += 1;
    sample.all += row.rssBytes;
    const type = (row.cmd.match(/--type=([a-zA-Z-]+)/) || [])[1] || "browser";
    if (type === "renderer") {
      sample.renderer += row.rssBytes;
      // Dedicated workers are THREADS in the renderer process on Chromium.
      sample.rendererThreads = Math.max(sample.rendererThreads, threadCount(row.pid));
      sample.rendererCount += 1;
    } else if (type === "gpu-process") sample.gpu += row.rssBytes;
    else if (type === "browser") sample.browser += row.rssBytes;
    else if (type === "utility") sample.utility += row.rssBytes;
    else sample.other += row.rssBytes;
  }
  return sample;
}

function systemSample() {
  const read = (cmd, cmdArgs) => {
    try { return execFileSync(cmd, cmdArgs, { encoding: "utf8" }); } catch { return ""; }
  };
  const swap = read("/usr/sbin/sysctl", ["vm.swapusage"]);
  const swapMatch = swap.match(/used = ([\d.]+)M.*free = ([\d.]+)M/);
  const vm = read("/usr/bin/vm_stat", []);
  const pageSize = Number((vm.match(/page size of (\d+)/) || [])[1] || 16384);
  const stat = (label) => Number((vm.match(new RegExp(`${label}:\\s+(\\d+)`)) || [])[1] || 0) * pageSize;
  const pressure = read("/usr/bin/memory_pressure", ["-Q"]);
  return {
    swapUsedMB: swapMatch ? Number(swapMatch[1]) : null,
    swapFreeMB: swapMatch ? Number(swapMatch[2]) : null,
    freeBytes: stat("Pages free"),
    compressedBytes: stat("Pages occupied by compressor"),
    swapinsPages: Number((vm.match(/Swapins:\s+(\d+)/) || [])[1] || 0),
    swapoutsPages: Number((vm.match(/Swapouts:\s+(\d+)/) || [])[1] || 0),
    freePercent: Number((pressure.match(/free percentage:\s+(\d+)/) || [])[1] || null)
  };
}

const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "cad-viewer-profile-"));
const browser = await chromium.launchPersistentContext(profileDir, {
  headless: true,
  viewport: { width: 1400, height: 900 },
  args: [
    "--use-angle=metal",
    "--enable-precise-memory-info",
    "--disable-features=PrivateNetworkAccessSendPreflights",
    "--disable-hang-monitor"
  ]
});

const samples = [];
const result = { file: args.file, crashed: false, crashMessage: "", loaded: false, samples, capabilities: {} };
let loaderState = { publishCount: 0, componentCount: 0, loadedComponents: 0, totalComponents: 0 };
let sampler = null;
let systemSampler = null;
let latestSystem = systemSample();
result.systemAtStart = latestSystem;

try {
  const page = await browser.newPage();
  await page.addInitScript(() => {
    window.__loaderProbe = { publishCount: 0, componentCount: 0, loadedComponents: 0, totalComponents: 0 };
    setInterval(() => {
      const cost = window.__cadMeshCost;
      if (cost) {
        window.__loaderProbe = {
          publishCount: Number(cost.publishCount) || 0,
          componentCount: Number(cost.componentCount) || 0,
          loadedComponents: Number(cost.loadedComponents) || 0,
          totalComponents: Number(cost.totalComponents) || 0,
          typedArrayBytes: Number(cost.componentTotalBytes) || 0,
          final: cost.final === true
        };
      }
    }, 100);
  });
  page.on("crash", () => { result.crashed = true; result.crashMessage = "renderer crash"; });

  const cdp = await browser.newCDPSession(page);
  await cdp.send("Performance.enable").catch(() => {});
  await cdp.send("Runtime.enable").catch(() => {});

  const started = Date.now();
  await page.goto(`${args.url.replace(/\/+$/, "")}/?file=${encodeURIComponent(args.file)}`,
    { waitUntil: "domcontentloaded", timeout: 120000 });

  result.capabilities = await page.evaluate(async () => {
    const out = { crossOriginIsolated: !!self.crossOriginIsolated, hasMeasureUA: typeof performance.measureUserAgentSpecificMemory === "function", measured: null, error: "" };
    if (out.hasMeasureUA) {
      try { out.measured = await performance.measureUserAgentSpecificMemory(); }
      catch (error) { out.error = String(error?.message || error); }
    }
    return out;
  }).catch((error) => ({ error: String(error?.message || error) }));

  // CDP metrics + loader state, on their own cadence and never blocking the ps sampler.
  let cdpBusy = false;
  let cdpHeap = { used: 0, total: 0, arrayBuffers: 0 };
  const pollCdp = async () => {
    if (cdpBusy) return;
    cdpBusy = true;
    try {
      const { metrics } = await cdp.send("Performance.getMetrics");
      const by = Object.fromEntries(metrics.map((metric) => [metric.name, metric.value]));
      const usage = await cdp.send("Runtime.getHeapUsage").catch(() => null);
      cdpHeap = {
        used: by.JSHeapUsedSize || usage?.usedSize || 0,
        total: by.JSHeapTotalSize || usage?.totalSize || 0,
        // Runtime.getHeapUsage's totalSize excludes external backing stores;
        // the difference against RSS is where ArrayBuffers live.
        arrayBuffers: usage ? (usage.embedderHeapUsedSize || 0) : 0,
        documents: by.Documents || 0,
        nodes: by.Nodes || 0
      };
      const probe = await page.evaluate(() => window.__loaderProbe).catch(() => null);
      if (probe) loaderState = probe;
    } catch { /* main thread pinned or target gone; ps sampling continues */ }
    cdpBusy = false;
  };
  const cdpTimer = setInterval(pollCdp, 250);

  sampler = setInterval(() => {
    const ps = psSample(profileDir);
    if (!ps) return;
    samples.push({
      tMs: Date.now() - started,
      ...ps,
      heapUsed: cdpHeap.used,
      heapTotal: cdpHeap.total,
      embedderHeap: cdpHeap.arrayBuffers,
      publishCount: loaderState.publishCount,
      componentCount: loaderState.componentCount,
      loadedComponents: loaderState.loadedComponents,
      totalComponents: loaderState.totalComponents,
      typedArrayBytes: loaderState.typedArrayBytes || 0,
      swapUsedMB: latestSystem.swapUsedMB,
      swapFreeMB: latestSystem.swapFreeMB,
      sysFreePercent: latestSystem.freePercent,
      sysCompressedBytes: latestSystem.compressedBytes
    });
  }, args.sampleMs);
  systemSampler = setInterval(() => { latestSystem = systemSample(); }, 2500);

  const deadline = started + args.timeoutMs;
  while (Date.now() < deadline && !result.crashed) {
    if (loaderState.final === true) { result.loaded = true; result.timeToLoadedMs = Date.now() - started; break; }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  clearInterval(cdpTimer);
  if (result.loaded) {
    await new Promise((resolve) => setTimeout(resolve, 5000));
    result.renderMemoryProbe = await page.evaluate(
      () => (typeof window.__cadRenderMemoryProbe === "function" ? window.__cadRenderMemoryProbe() : null)
    ).catch(() => null);
  } else if (!result.crashed) {
    result.crashMessage = `timeout after ${args.timeoutMs} ms`;
  }
  result.systemAtEnd = systemSample();
} finally {
  if (sampler) clearInterval(sampler);
  if (systemSampler) clearInterval(systemSampler);
  await browser.close().catch(() => {});
  fs.rmSync(profileDir, { recursive: true, force: true });
}

// ------------------------------------------------------------------- reporting
const peakOf = (field) => samples.reduce((best, sample) =>
  (sample[field] > (best?.[field] ?? -1) ? sample : best), null);
const report = {};
for (const field of ["renderer", "gpu", "all", "browser", "utility", "heapUsed", "heapTotal", "rendererThreads"]) {
  const peak = peakOf(field);
  report[field] = peak ? {
    value: peak[field], tMs: peak.tMs,
    publishCount: peak.publishCount, loadedComponents: peak.loadedComponents,
    totalComponents: peak.totalComponents, typedArrayBytes: peak.typedArrayBytes,
    rendererThreads: peak.rendererThreads, processCount: peak.processCount,
    swapUsedMB: peak.swapUsedMB, swapFreeMB: peak.swapFreeMB, sysFreePercent: peak.sysFreePercent
  } : null;
}
result.peaks = report;
result.sampleCount = samples.length;

process.stderr.write(`\nloaded=${result.loaded} crashed=${result.crashed} ${result.crashMessage}\n`);
process.stderr.write(`samples=${samples.length} over ${result.timeToLoadedMs ?? "?"} ms\n`);
process.stderr.write(`capabilities=${JSON.stringify(result.capabilities)}\n`);
for (const [field, peak] of Object.entries(report)) {
  if (!peak) continue;
  const value = field.includes("Thread") ? String(peak.value) : fmt(peak.value);
  process.stderr.write(`  peak ${field.padEnd(16)} ${value.padStart(10)}  @ ${String(peak.tMs).padStart(7)} ms  publish=${peak.publishCount}  comps=${peak.loadedComponents}/${peak.totalComponents}  threads=${peak.rendererThreads}  swap used=${peak.swapUsedMB}M free=${peak.swapFreeMB}M  sysFree=${peak.sysFreePercent}%\n`);
}
process.stderr.write(`system at start: ${JSON.stringify(result.systemAtStart)}\n`);
process.stderr.write(`system at end:   ${JSON.stringify(result.systemAtEnd)}\n`);
if (result.renderMemoryProbe) process.stderr.write(`renderMemoryProbe: ${JSON.stringify(result.renderMemoryProbe)}\n`);
if (args.out) fs.writeFileSync(args.out, `${JSON.stringify(result, null, 2)}\n`);
