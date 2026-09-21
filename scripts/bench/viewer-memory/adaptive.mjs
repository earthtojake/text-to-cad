#!/usr/bin/env node
// Bounded loading and interaction checks using the default camera-driven LOD.
// Uses one caller-owned viewer and one disposable browser. Never starts/stops a server.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { viewerRuntimeFingerprint, verifyServedViewerClient } from './fingerprint.mjs';
import { installWorkerProbe } from './worker-probe.mjs';
import { installViewerResourceTiming, collectViewerResourceTiming } from './resource-timing.mjs';
import { installCacheWriteProbe, collectHeapDiagnostics } from './heap-diagnostics.mjs';
import { adaptiveStatus, preservesCompleteAdaptiveView, createAdaptiveStabilityWindow, finishAdaptiveSettlePhase, adaptiveSettleAssertions, gradeAdaptiveOutcome, summarizeIntervals, processMemoryFromPs, mergeProcessPeak } from './adaptive-support.mjs';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const require = createRequire(new URL('../../../apps/viewer/package.json', import.meta.url));
const { chromium } = require(process.env.PLAYWRIGHT_FROM || 'playwright');
const args = { timeoutMs: 180000, maxRendererMiB: 2048 };
const flags = { '--url': 'url', '--file': 'file', '--out': 'out', '--screenshot': 'screenshot',
  '--components': 'components', '--occurrences': 'occurrences', '--server-provenance': 'serverProvenance',
  '--cache-state': 'cacheState',
  '--resize-to': 'resizeTo',
  '--timeout-ms': 'timeoutMs', '--max-renderer-mib': 'maxRendererMiB' };
for (let index = 2; index < process.argv.length; index += 2) {
  const key = flags[process.argv[index]], value = process.argv[index + 1];
  if (!key || !value) throw new Error(`Unknown/incomplete option: ${process.argv[index]}`);
  args[key] = value;
}
for (const key of ['components', 'occurrences', 'timeoutMs', 'maxRendererMiB']) args[key] = Number(args[key]);
if (!args.url || !args.file || !args.out || ![args.components, args.occurrences].every(n => Number.isInteger(n) && n > 0)) {
  throw new Error('Usage: adaptive.mjs --url ORIGIN --file hand.step --components 866 --occurrences 3259 --out REPORT.json [--screenshot IMAGE.png]');
}
if (!(args.timeoutMs > 0 && args.timeoutMs <= 180000) || !(args.maxRendererMiB > 0 && args.maxRendererMiB <= 2048)) {
  throw new Error('Deadline must be at most 180000 ms and renderer bound at most 2048 MiB');
}
if (args.resizeTo && !/^\d{3,4}x\d{3,4}$/.test(args.resizeTo)) throw new Error('--resize-to requires WIDTHxHEIGHT');
args.screenshot ||= args.out.replace(/\.json$/, '') + '.png';
fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
fs.mkdirSync(path.dirname(path.resolve(args.screenshot)), { recursive: true });
const expected = { components: args.components, occurrences: args.occurrences };
const report = { args, startedAt: new Date().toISOString(),
  qualification: 'Default camera-driven LOD, no minimum override. Source-free saved-file view; cache state recorded separately. No allocation sampling or forced GC before grading. Screenshot and failure diagnostics occur after grading. Frame intervals are browser cadence, not GPU completion.',
  cacheState: args.cacheState || 'Existing caller-owned cache; exact warmth not asserted',
  environment: { node: process.version, cpu: os.cpus()[0]?.model, platform: process.platform, arch: process.arch },
  runtimeFingerprintAtStart: viewerRuntimeFingerprint(), phases: [], samples: [], peakRss: {},
  errors: [], responseFailures: [], limitations: [], assertions: {}, };
report.harness = Object.fromEntries(['adaptive.mjs', 'adaptive-support.mjs', 'resource-timing.mjs'].map(name => [name,
  createHash('sha256').update(fs.readFileSync(new URL(name, import.meta.url))).digest('hex')]));
report.playwright = { resolvedEntry: require.resolve(process.env.PLAYWRIGHT_FROM || 'playwright') };
if (args.serverProvenance) report.serverProvenance = JSON.parse(fs.readFileSync(args.serverProvenance, 'utf8'));

// Verify actual installs against their locks; BVH belongs to cadgen-js and need
// not be a direct app dependency. Also prove emitted worker bytes, not just HTML.
async function verifyAssets() {
  const proof = await verifyServedViewerClient(args.url);
  const dependencies = viewerRuntimeFingerprint().installedDependencies;
  for (const [root, names] of [['apps/viewer', ['three', 'react']], ['packages/cadgen-js', ['three', 'three-mesh-bvh']]]) {
    const lock = JSON.parse(fs.readFileSync(path.join(repo, root, 'package-lock.json')));
    for (const name of names) {
      const locked = lock.packages[`node_modules/${name}`]?.version;
      if (!locked || dependencies[root][name]?.version !== locked) throw new Error(`Installed ${root}/${name} differs from lock`);
    }
  }
  const assets = path.join(proof.dist, 'assets');
  const workers = fs.readdirSync(assets).filter(name => /worker.*\.js$/i.test(name));
  if (!workers.some(name => /^surfWorker-/.test(name)) || !workers.some(name => /^raycastBvhWorker-/.test(name))) {
    throw new Error('Production SURF/BVH worker assets are missing');
  }
  proof.workers = [];
  for (const name of workers) {
    const pathname = `/assets/${name}`;
    const response = await fetch(new URL(pathname, args.url), { signal: AbortSignal.timeout(5000), cache: 'no-store' });
    if (!response.ok || !/javascript/.test(response.headers.get('content-type') || '')) throw new Error(`Worker asset failed: ${pathname}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    if (!bytes.equals(fs.readFileSync(path.join(assets, name)))) throw new Error(`Worker bytes differ: ${pathname}`);
    proof.workers.push({ path: pathname, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
  }
  return proof;
}

function installAdaptiveProbe() {
  const stats = { draws: 0, lastAt: 0, firstGeometryAt: null, lodCount: 0, refinements: 0,
    coarsenings: 0, cameraCount: 0, limitations: [], levels: {}, lodTail: [], motion: null };
  window.__adaptiveProbe = stats;
  for (const proto of [window.WebGLRenderingContext?.prototype, window.WebGL2RenderingContext?.prototype]) {
    if (!proto || Object.hasOwn(proto, '__adaptivePatched')) continue;
    proto.__adaptivePatched = true;
    for (const name of ['drawElements', 'drawArrays', 'drawElementsInstanced', 'drawArraysInstanced']) {
      const original = proto[name]; if (typeof original !== 'function') continue;
      proto[name] = function () {
        stats.draws++; stats.lastAt = performance.now();
        if (stats.firstGeometryAt === null && arguments[0] === this.TRIANGLES && window.__cadMeshCost?.componentCount > 0) stats.firstGeometryAt = stats.lastAt;
        return original.apply(this, arguments);
      };
    }
  }
  for (const name of ['pointermove', 'wheel', 'keydown']) window.addEventListener(name, () => stats.cameraCount++, { passive: true });
  window.addEventListener('cad:lod-level', event => {
    const { cid, level } = event.detail || {};
    if (typeof cid !== 'string' || !Number.isFinite(level)) return;
    const previous = stats.levels[cid] ?? 0; stats.levels[cid] = level;
    stats.lodCount++; if (level > previous) stats.refinements++; if (level < previous) stats.coarsenings++;
    stats.lodTail.push({ cid, level, at: performance.now() }); if (stats.lodTail.length > 64) stats.lodTail.shift();
  });
  window.addEventListener('cad:memory-limitation', event => {
    const { cid, level, kind, category, label, reason } = event.detail || {};
    stats.limitations.push({ cid, level, kind, category, label, reason, at: performance.now() });
    if (stats.limitations.length > 64) stats.limitations.shift();
  });
  const frame = now => {
    const motion = stats.motion;
    if (motion?.active) {
      if (motion.last !== null && motion.intervals.length < 10000) motion.intervals.push(now - motion.last);
      motion.last = now;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'viewer-adaptive-'));
let context, page, sampler, watchdog, deadline, stopReason = '', lastSample = null, completeObserved = false;
const sampleRss = () => {
  try { return processMemoryFromPs(execFileSync('/bin/ps', ['-axww', '-o', 'pid=,ppid=,rss=,args='], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 }), profile); }
  catch { return null; }
};
async function bounded(promise, maximum = 5000) {
  let timer;
  try { return await Promise.race([promise, new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error('bounded renderer operation timed out')), Math.max(1, Math.min(maximum, deadline ? deadline - Date.now() : maximum)));
  })]); } finally { clearTimeout(timer); }
}
function checkStop() {
  if (stopReason) throw new Error(stopReason);
  if (Date.now() >= deadline) throw new Error('180-second-or-shorter acceptance deadline');
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function snapshot(label) {
  checkStop();
  const sample = await bounded(page.evaluate(label => {
    const a = window.__adaptiveProbe, entries = window.__cadSceneSync?.entries || [];
    return { label, at: performance.now(), modelKey: window.__cadModelPlacement?.modelKey || '',
      meshCost: window.__cadMeshCost ? { ...window.__cadMeshCost, composed: { ...window.__cadMeshCost.composed } } : null,
      renderMemoryProbe: window.__cadRenderMemoryProbe?.() || null,
      sceneSync: entries.length ? { ...entries.at(-1) } : null,
      memoryPolicy: window.__cadViewerMemoryPolicySnapshot?.() || null,
      viewportLod: window.__cadViewportLod?.() || null,
      sceneAdoption: window.__cadLodSceneAdoption?.() || null,
      workers: { ...window.__cadWorkerProbe }, cacheWrites: { ...window.__cadCacheWriteProbe },
      draw: { count: a.draws, lastAt: a.lastAt, firstGeometryAt: a.firstGeometryAt },
      events: { lodCount: a.lodCount, refinements: a.refinements, coarsenings: a.coarsenings, cameraCount: a.cameraCount },
      cameraZoomPercent: document.querySelector('input[aria-label="Zoom level percent"]')?.value || null,
      limitations: a.limitations.slice(), lodTail: a.lodTail.slice(),
      selectedRows: [...document.querySelectorAll('[role="treeitem"][aria-selected="true"]')].map(row => ({ id: row.dataset.stepTreeNodeId, label: row.getAttribute('aria-label') })),
    };
  }, label));
  sample.observedAt = new Date().toISOString();
  const status = adaptiveStatus(sample, expected);
  // Publishing a new LOD meshCost can precede React's scene commit. The old
  // complete draw is valid during that interval; only stable() demands that
  // the newest publication has also reached the scene.
  if (completeObserved && !preservesCompleteAdaptiveView(sample, expected, report.initialComplete.modelKey)) throw new Error('Previously complete view lost occurrences or changed model');
  if (status.complete && !completeObserved) { completeObserved = true; report.initialComplete = { modelKey: sample.modelKey, at: sample.at, observedAt: sample.observedAt, firstGeometryAt: sample.draw.firstGeometryAt }; }
  if (report.samples.length < 512) report.samples.push(sample);
  lastSample = sample;
  checkStop();
  return sample;
}
async function stable(label, phaseMs, allowRecovery = false) {
  const phase = { kind: 'settle', label, phaseLimitMs: phaseMs, startedAt: new Date().toISOString(), complete: false };
  report.phases.push(phase);
  const until = Math.min(deadline, Date.now() + phaseMs), update = createAdaptiveStabilityWindow();
  let p = lastSample, status = null;
  while (Date.now() < until) {
    p = await snapshot(label); status = update(p, expected, Date.now());
    if (status.stable) break;
    await pause(500);
  }
  checkStop();
  return finishAdaptiveSettlePhase(phase, { sample: p, status, finishedAt: new Date().toISOString(), allowRecovery });
}
async function motion(label, action) {
  await bounded(page.evaluate(() => { const a = window.__adaptiveProbe; a.motion = { active: true, intervals: [], last: null, drawBase: a.draws }; }));
  const at = Date.now(); await action();
  const p = await bounded(page.evaluate(() => { const a = window.__adaptiveProbe, m = a.motion; m.active = false; return { intervals: m.intervals, draws: a.draws - m.drawBase }; }));
  const phase = { label, durationMs: Date.now() - at, frames: summarizeIntervals(p.intervals.slice(2)),
    warmupIntervalsExcluded: 2, rawFrameIntervalsMs: p.intervals, draws: p.draws };
  report.phases.push(phase); await snapshot(label);
  if (!(phase.frames.samples > 10 && phase.draws > 0)) throw new Error(`${label}: insufficient rendered interaction frames`);
  return phase;
}

try {
  report.servedClientProof = await verifyAssets();
  context = await chromium.launchPersistentContext(profile, { headless: true, viewport: { width: 1400, height: 900 },
    args: ['--use-angle=metal', '--enable-precise-memory-info', '--disable-hang-monitor', '--disable-features=PrivateNetworkAccessSendPreflights'] });
  report.browserVersion = context.browser()?.version();
  page = context.pages()[0] || await context.newPage();
  await page.addInitScript(installWorkerProbe); await page.addInitScript(installCacheWriteProbe); await page.addInitScript(installAdaptiveProbe);
  await page.addInitScript(installViewerResourceTiming);
  page.on('pageerror', error => report.errors.push(String(error)));
  page.on('console', message => {
    if (message.type() !== 'error') return;
    if (message.location()?.url.includes('/__tess_cache/') && /404/.test(message.text())) return;
    if (report.errors.length < 100) report.errors.push(`console: ${message.text().slice(0, 500)}`);
  });
  page.on('crash', () => { stopReason = 'renderer crashed'; });
  page.on('response', response => { if (response.status() >= 400) report.responseFailures.push({ url: response.url(), status: response.status() }); });
  // No __CAD_VIEWER_* overrides: use the production default camera policy.
  deadline = Date.now() + args.timeoutMs;
  const sample = () => {
    const rss = sampleRss(); mergeProcessPeak(report.peakRss, rss);
    if (report.peakRss.renderer?.largestPidBytes > args.maxRendererMiB * 1048576) {
      stopReason ||= 'largest renderer exceeded bounded RSS limit';
    }
  };
  sampler = setInterval(sample, 500);
  watchdog = setTimeout(() => { stopReason ||= 'acceptance deadline'; context?.close().catch(() => {}); }, args.timeoutMs + 1000);
  report.navigationStartedAt = new Date().toISOString();
  await bounded(page.goto(`${args.url.replace(/\/+$/, '')}/?file=${encodeURIComponent(args.file)}`, { waitUntil: 'domcontentloaded', timeout: Math.min(60000, args.timeoutMs) }), 60000);
  const initial = await stable('initial-default-idle', 60000);
  if (args.resizeTo) {
    const [width, height] = args.resizeTo.split('x').map(Number);
    report.resize = { original: { width: 1400, height: 900 }, requested: { width, height }, observations: [] };
    for (const [label, viewport] of [['resized', report.resize.requested], ['restored', report.resize.original]]) {
      await bounded(page.setViewportSize(viewport));
      await bounded(page.waitForFunction(() => window.__cadViewportLod?.().pendingEvaluation === true, null, { timeout: 3000 }), 3500);
      const pending = await snapshot(`${label}-pending-evaluation`);
      report.resize.observations.push({ label, viewport, pendingEvaluation: pending.viewportLod.pendingEvaluation, visibility: pending.viewportLod.visibility });
      await stable(`${label}-default-idle`, 10000, true);
    }
  }
  const canvasIndex = await bounded(page.locator('canvas').evaluateAll(nodes => nodes.map((node, index) => {
    const rect = node.getBoundingClientRect(); return { index, area: rect.width * rect.height };
  }).sort((a, b) => b.area - a.area)[0]?.index));
  const canvas = page.locator('canvas').nth(canvasIndex ?? 0);
  const box = await bounded(canvas.boundingBox());
  if (!box || box.width < 100 || box.height < 100) throw new Error('Visible CAD canvas unavailable');
  const center = { x: box.x + box.width * .5, y: box.y + box.height * .5 };
  await bounded(page.getByRole('button', { name: 'Orbit', exact: true }).click());
  await bounded(page.mouse.move(center.x, center.y));
  await motion('orbit', async () => {
    await bounded(page.mouse.down());
    for (let i = 0; i < 100; i++) {
      checkStop(); await bounded(page.mouse.move(center.x + 70 * Math.sin(i * Math.PI / 25), center.y + 40 * (1 - Math.cos(i * Math.PI / 25))));
      if (i % 10 === 0) await snapshot('orbit');
      await pause(50);
    }
    await bounded(page.mouse.up());
  });
  await bounded(page.getByRole('button', { name: 'Exit orbit', exact: true }).click());
  report.wheelSequence = [-250, -250, -250, -250];
  await motion('zoom-in', async () => {
    await bounded(page.mouse.move(center.x, center.y));
    for (const delta of report.wheelSequence) { checkStop(); await bounded(page.mouse.wheel(0, delta)); await pause(300); }
  });
  const near = await stable('near-default-idle', 30000, true);
  await motion('zoom-out', async () => {
    for (const delta of [...report.wheelSequence].reverse()) { checkStop(); await bounded(page.mouse.wheel(0, -delta)); await pause(300); }
  });
  const far = await stable('returned-default-idle', 30000, true);
  // Pick one visible occurrence by its own tree row, without demanding an
  // entire assembly's topology. The row identity and method remain in the report.
  const row = page.locator('[role="treeitem"][data-step-tree-node-type="part"]:visible').first();
  for (let depth = 0; depth < 8 && !(await bounded(row.count())); depth++) {
    const branch = page.locator('[role="treeitem"][data-step-tree-node-type="assembly"][aria-expanded="false"]:visible').first();
    if (!(await bounded(branch.count()))) break;
    await bounded(branch.locator('button[aria-label^="Expand "]').first().click());
    await pause(200);
  }
  if (!(await bounded(row.count()))) throw new Error('No visible occurrence tree row for selection check');
  report.selection = { id: await row.getAttribute('data-step-tree-node-id'), label: await row.getAttribute('aria-label'), method: 'occurrence-tree-row' };
  // Focus+Enter selects the row itself, never an embedded expand/menu control.
  await bounded(row.focus()); await bounded(row.press('Enter'));
  await bounded(page.waitForFunction(id => document.querySelector(`[data-step-tree-node-id="${CSS.escape(id)}"]`)?.getAttribute('aria-selected') === 'true', report.selection.id));
  await snapshot('selected');
  // A second activation toggles this same occurrence off. Escape closes the
  // panel and can leave selection active, so row absence is never a clear proof.
  await bounded(row.press('Enter'));
  await bounded(page.waitForFunction(id => document.querySelector(`[data-step-tree-node-id="${CSS.escape(id)}"]`)?.getAttribute('aria-selected') === 'false', report.selection.id));
  report.selection.clearMethod = 'same-row-toggle-confirmed-present';
  await bounded(page.mouse.move(10, 10)); await pause(300);
  const cleared = await snapshot('selection-cleared');
  if (cleared.selectedRows.some(value => value.id === report.selection.id)) throw new Error('Occurrence selection did not clear');
  const idleUntil = Math.min(deadline, Date.now() + 10000);
  while (Date.now() < idleUntil) { await snapshot('final-idle'); await pause(500); }
  const final = await stable('final-stable', 10000, true);
  sample(); checkStop();
  const phases = report.phases.filter(value => value.kind === 'settle');
  const orbit = report.phases.find(value => value.label === 'orbit');
  report.interactionCriteria = { orbitP95MsStrictlyBelow: 33, orbitMaxMsAtMost: 250,
    qualification: 'PLAN orbit p95 target; maximum is an additional explicit harness guard. Zoom cadence is reported separately. First two rAF intervals excluded, matching the medium lifecycle method.' };
  report.assertions = {
    completeScene: completeObserved && adaptiveStatus(final, expected).complete,
    defaultPolicy: final.viewportLod.minimumLevel === 0,
    adaptiveExercised: near.events.refinements > initial.events.refinements || near.limitations.length > initial.limitations.length,
    ...adaptiveSettleAssertions(phases),
    interactionRendered: report.phases.filter(value => value.frames).every(value => value.draws > 0 && value.frames.samples > 10),
    orbitCadence: orbit.frames.p95 < 33,
    orbitMaxGuard: orbit.frames.max <= 250,
    selectionCleared: true,
    ...(args.resizeTo ? { resizedPolicyReevaluated: report.resize.observations.length === 2 && report.resize.observations.every(value => value.pendingEvaluation) } : {}),
    withinRssBound: report.peakRss.renderer?.largestPidBytes > 0 && report.peakRss.renderer.largestPidBytes <= args.maxRendererMiB * 1048576,
    noPageErrors: report.errors.length === 0,
    noUnexpectedHttpErrors: report.responseFailures.every(value => value.status === 404 && value.url.includes('/__tess_cache/')),
  };
  report.returnedFarView = { initialLevels: initial.viewportLod.levelCounts, returnedLevels: far.viewportLod.levelCounts, coarseningEvents: far.events.coarsenings - near.events.coarsenings };
  report.softSettleFailures = phases.filter(value => !value.complete).map(value => ({ label: value.label, failure: value.failure }));
  if (report.softSettleFailures.length) report.failure = report.softSettleFailures.map(value => value.failure).join('; ');
  report.outcome = gradeAdaptiveOutcome(report.assertions, phases);
} catch (error) {
  report.outcome = 'failed'; report.failure = stopReason || String(error.message || error);
} finally {
  clearInterval(sampler); clearTimeout(watchdog);
  report.gradedAt = new Date().toISOString(); report.lastSample = lastSample;
  // Screenshot/GC cannot turn a failed pre-diagnostic grade into a pass.
  deadline = Date.now() + 15000;
  if (page && !page.isClosed()) {
    try {
      report.resourceTiming = await bounded(page.evaluate(collectViewerResourceTiming, { cutoffEpochMs: Date.parse(report.gradedAt) }), 2500);
    } catch (error) { report.resourceTimingError = String(error.message || error); }
    try {
      await bounded(page.screenshot({ path: args.screenshot, timeout: 4000 }), 4500);
      report.screenshot = { path: path.resolve(args.screenshot), capturedAfterGrade: true, requiresVisualReview: true };
    } catch (error) { report.screenshotError = String(error.message || error); }
    if (report.outcome === 'failed') {
      try {
        const cdp = await context.newCDPSession(page);
        report.failureDiagnostics = await collectHeapDiagnostics({ page, cdp, bounded, sampleRss, failed: true, sampling: false });
      } catch (error) { report.diagnosticsError = String(error.message || error); }
    }
  }
  await context?.close().catch(() => {});
  fs.rmSync(profile, { recursive: true, force: true });
  report.runtimeFingerprintAtEnd = viewerRuntimeFingerprint();
  report.runtimeUnchanged = JSON.stringify(report.runtimeFingerprintAtStart) === JSON.stringify(report.runtimeFingerprintAtEnd);
  if (!report.runtimeUnchanged) report.outcome = 'invalid-runtime-changed';
  report.finishedAt = new Date().toISOString();
  fs.writeFileSync(args.out, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ outcome: report.outcome, failure: report.failure, initialComplete: report.initialComplete,
    peakRendererMiB: (report.peakRss.renderer?.largestPidBytes || 0) / 1048576, assertions: report.assertions, out: args.out, screenshot: report.screenshot }));
}
if (report.outcome !== 'passed-default-adaptive') process.exitCode = 1;
