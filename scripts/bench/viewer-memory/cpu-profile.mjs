#!/usr/bin/env node
// Headless CDP CPU profile of a viewer load: aggregates self time by function
// (name + script + line) from first navigation to the final publish (+ settle),
// and prints the scene-sync seam. Never touches the user's browser.
// Usage: node cpu-profile.mjs --url http://127.0.0.1:3420 --file <root-relative> [--top 40]
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_FROM || "/Users/jakefitzgerald/robots/text-to-cad/apps/viewer/node_modules/playwright");
const args = { url: "http://127.0.0.1:3420", file: "", top: 40, timeoutMs: 600000, out: "" };
const argv = process.argv.slice(2);
for (let i = 0; i < argv.length; i += 1) {
  if (argv[i] === "--url") args.url = argv[++i];
  else if (argv[i] === "--file") args.file = argv[++i];
  else if (argv[i] === "--top") args.top = Number(argv[++i]);
  else if (argv[i] === "--timeout-ms") args.timeoutMs = Number(argv[++i]);
  else if (argv[i] === "--out") args.out = argv[++i];
}
const profileDir = fs.mkdtempSync(path.join(os.tmpdir(), "cad-viewer-cpu-"));
const browser = await chromium.launchPersistentContext(profileDir, {
  headless: true, viewport: { width: 1400, height: 900 },
  args: ["--use-angle=metal", "--disable-features=PrivateNetworkAccessSendPreflights", "--disable-hang-monitor"]
});
try {
  const page = await browser.newPage();
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Profiler.enable");
  await cdp.send("Profiler.setSamplingInterval", { interval: 500 });
  await cdp.send("Profiler.start");
  const started = Date.now();
  await page.goto(`${args.url.replace(/\/+$/, "")}/?file=${encodeURIComponent(args.file)}`, { waitUntil: "domcontentloaded" });
  let loaded = false;
  while (Date.now() - started < args.timeoutMs) {
    const probe = await page.evaluate(() => ({ modelKey: window.__cadModelPlacement?.modelKey || "", final: window.__cadMeshCost?.final === true }));
    if (probe.modelKey && probe.final) { loaded = true; break; }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const loadedMs = Date.now() - started;
  await page.waitForTimeout(3000);
  const { profile } = await cdp.send("Profiler.stop");
  const seam = await page.evaluate(() => window.__cadSceneSync ? JSON.parse(JSON.stringify(window.__cadSceneSync)) : null);
  // Self time per node = samples * interval; aggregate by callFrame.
  const byFrame = new Map();
  const nodeById = new Map(profile.nodes.map((node) => [node.id, node]));
  const deltas = profile.timeDeltas;
  const totalMs = deltas.reduce((sum, delta) => sum + delta, 0) / 1000;
  for (let i = 0; i < profile.samples.length; i += 1) {
    const node = nodeById.get(profile.samples[i]);
    if (!node) continue;
    const frame = node.callFrame;
    const key = `${frame.functionName || "(anonymous)"} ${path.basename(frame.url || "") || "(native)"}:${frame.lineNumber + 1}`;
    byFrame.set(key, (byFrame.get(key) || 0) + (deltas[i] || 0) / 1000);
  }
  // Inclusive time per function name (walk parents).
  const parentById = new Map();
  for (const node of profile.nodes) for (const child of node.children || []) parentById.set(child, node.id);
  const inclusive = new Map();
  for (let i = 0; i < profile.samples.length; i += 1) {
    const seen = new Set();
    let id = profile.samples[i];
    while (id !== undefined) {
      const node = nodeById.get(id);
      const frame = node.callFrame;
      const key = `${frame.functionName || "(anonymous)"} ${path.basename(frame.url || "") || "(native)"}`;
      if (!seen.has(key)) { seen.add(key); inclusive.set(key, (inclusive.get(key) || 0) + (deltas[i] || 0) / 1000); }
      id = parentById.get(id);
    }
  }
  const top = (map) => [...map.entries()].sort((a, b) => b[1] - a[1]).slice(0, args.top);
  process.stderr.write(`loaded=${loaded} in ${loadedMs} ms; profile ${Math.round(totalMs)} ms sampled\n`);
  process.stderr.write(`scene syncs: ${JSON.stringify(seam?.entries?.map((entry) => `${entry.mode[0]}${entry.ms}(${entry.records})${entry.reason ? `[${entry.reason}]` : ""}`))}\n`);
  process.stderr.write("--- self time (ms) ---\n");
  for (const [key, ms] of top(byFrame)) process.stderr.write(`${ms.toFixed(0).padStart(7)}  ${key}\n`);
  process.stderr.write("--- inclusive time (ms) ---\n");
  for (const [key, ms] of top(inclusive)) process.stderr.write(`${ms.toFixed(0).padStart(7)}  ${key}\n`);
  if (args.out) fs.writeFileSync(args.out, JSON.stringify({ loaded, loadedMs, seam, self: top(byFrame), inclusive: top(inclusive) }, null, 2));
} finally {
  await browser.close().catch(() => {});
  fs.rmSync(profileDir, { recursive: true, force: true });
}
