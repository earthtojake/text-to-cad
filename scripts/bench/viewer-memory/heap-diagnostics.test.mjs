import assert from 'node:assert/strict';
import { test } from 'node:test';
import vm from 'node:vm';
import { collectHeapDiagnostics, installCacheWriteProbe, summarizeSamplingProfile } from './heap-diagnostics.mjs';
import { installWorkerProbe } from './worker-probe.mjs';

test('cache probe counts unsettled bytes and releases successful and failed writes', async () => {
  const calls = [];
  const window = { fetch: (...args) => new Promise((resolve, reject) => calls.push({ args, resolve, reject })) };
  vm.runInNewContext(`(${installCacheWriteProbe.toString()})()`, { window });
  const first = window.fetch('/__tess_cache/a.tess', { method: 'POST', body: new Uint8Array(32) });
  const second = window.fetch('/__tess_cache/b.tess', { method: 'POST', body: new Uint8Array(48) });
  assert.equal(window.__cadCacheWriteProbe.activeBytes, 80);
  calls[0].resolve({ ok: true });
  await first;
  assert.equal(window.__cadCacheWriteProbe.activeBytes, 48);
  calls[1].reject(new Error('write failed'));
  await assert.rejects(second, /write failed/);
  assert.equal(window.__cadCacheWriteProbe.activeBytes, 0);
  assert.equal(window.__cadCacheWriteProbe.peakBytes, 80);
  assert.equal(window.__cadCacheWriteProbe.totalBytes, 80);
});

test('diagnostic worker stop terminates only live workers and is idempotent', () => {
  let nativeTerminations = 0;
  const window = { Worker: class { terminate() { nativeTerminations += 1; } } };
  vm.runInNewContext(`(${installWorkerProbe.toString()})()`, { window });
  const first = new window.Worker();
  new window.Worker();
  first.terminate();
  assert.equal(window.__cadStopMemoryProbeWorkers(), 1);
  assert.equal(window.__cadStopMemoryProbeWorkers(), 0);
  assert.equal(nativeTerminations, 2);
  assert.equal(window.__cadWorkerProbe.live, 0);
  new window.Worker();
  assert.equal(nativeTerminations, 3, 'a queued publication restarted work after diagnostic stop');
  assert.equal(window.__cadWorkerProbe.live, 0);
});

test('sampling summary retains allocation provenance and sorts largest live sites', () => {
  const summary = summarizeSamplingProfile({ head: {
    callFrame: { functionName: 'root', url: 'viewer.js', lineNumber: 0 }, selfSize: 1,
    children: [{ callFrame: { functionName: 'allocate', url: 'mesh.js', lineNumber: 9 }, selfSize: 80, children: [] }],
  } });
  assert.equal(summary.sampledBytes, 81);
  assert.equal(summary.largestSites[0].site, 'allocate mesh.js:10');
  assert.deepEqual(summary.largestSites[0].callers, ['root viewer.js:1']);
});

test('a sampling failure preserves heap evidence and still collects after a failed load', async () => {
  const calls = [];
  const cdp = { send: async method => {
    calls.push(method);
    if (method === 'Target.getTargets') return { targetInfos: [] };
    if (method === 'HeapProfiler.getSamplingProfile') throw new Error('sampling unavailable');
    if (method === 'HeapProfiler.stopSampling') return { profile: {} };
    return { usedSize: 12 };
  } };
  let reads = 0;
  const page = { evaluate: async () => ++reads === 1 ? 2 : { heapUsed: 20 }, url: () => 'http://127.0.0.1/' };
  const result = await collectHeapDiagnostics({ page, cdp, bounded: promise => promise,
    sampleRss: () => ({ renderer: { rssBytes: 100 } }), failed: true, sampling: true });
  assert.equal(result.before.page.usedSize, 12);
  assert.equal(result.after.state.heapUsed, 20);
  assert.equal(result.stoppedWorkers, 2);
  assert.equal(result.workersStopped, true);
  assert.equal(result.mainThreadQuiescenceVerified, false);
  assert.equal(result.errors[0].phase, 'before-sampling');
  assert.equal(calls.filter(method => method === 'HeapProfiler.collectGarbage').length, 2);
});
