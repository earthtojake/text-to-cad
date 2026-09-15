import assert from 'node:assert/strict';
import test from 'node:test';
import vm from 'node:vm';
import { installViewerResourceTiming, collectViewerResourceTiming } from './resource-timing.mjs';

function fixture(resources) {
  let requestedSize, full;
  const performance = { timeOrigin: 1000, now: () => 300,
    setResourceTimingBufferSize: n => { requestedSize = n; },
    addEventListener: (name, fn) => { assert.equal(name, 'resourcetimingbufferfull'); full = fn; },
    getEntriesByType: kind => { assert.equal(kind, 'resource'); return resources; } };
  const context = vm.createContext({ window: { location: { origin: 'http://localhost:3267' } }, performance, URL });
  vm.runInContext(`(${installViewerResourceTiming.toString()})()`, context);
  return { context, full: () => full(), requestedSize: () => requestedSize,
    collect: (cutoff = 1250) => JSON.parse(JSON.stringify(vm.runInContext(
      `(${collectViewerResourceTiming.toString()})({cutoffEpochMs:${cutoff}})`, context))) };
}
function entry(name, changes = {}) {
  return { name, entryType: 'resource', initiatorType: 'fetch', nextHopProtocol: 'http/1.1',
    startTime: 100, duration: 40, fetchStart: 100, requestStart: 102, responseStart: 130, responseEnd: 140,
    transferSize: 1300, encodedBodySize: 1000, decodedBodySize: 1000, responseStatus: 200, ...changes };
}

test('collects same-origin cache/SURF phases after grading without copying body or query data', () => {
  const ignoredBody = { expensive: true };
  const f = fixture([
    entry('http://localhost:3267/__tess_cache/cid.L1.tess', { body: ignoredBody }),
    entry('http://localhost:3267/__tess_cache/batch'),
    entry('http://localhost:3267/__cad/store?file=%2Fprivate%2Ftree%2Fcomponents%2Fcid.surf&secret=x'),
    entry('http://localhost:3267/files/cid2.surf'),
    entry('http://other-origin/__tess_cache/private.tess'), entry('http://localhost:3267/assets/main.js'),
    entry('http://localhost:3267/__cad/store?file=private.step'),
  ]);
  assert.equal(f.requestedSize(), 8192);
  const result = f.collect();
  assert.equal(result.installed, true); assert.equal(result.truncated, false);
  assert.deepEqual(result.entries.map(e => [e.route, e.key]), [
    ['tess-entry', 'cid.L1.tess'], ['tess-batch', ''], ['surf', 'cid.surf'], ['surf', 'cid2.surf']]);
  assert.equal(result.entries[0].requestStart, 102); assert.equal(result.entries[0].responseStart, 130);
  assert.equal(result.entries[0].encodedBodySize, 1000);
  assert.equal(result.entries[0].body, undefined); assert.ok(!JSON.stringify(result).includes('secret'));
  assert.equal(result.timeOrigin, 1000); assert.equal(result.cutoffAt, 250); assert.equal(result.collectedAfterGrade, true);
});

test('preserves cache/opaque zeros, unsupported values and repeated URL requests without inventing methods', () => {
  const url = 'http://localhost:3267/__tess_cache/cid.tess';
  const f = fixture([entry(url, { transferSize: 0, responseStart: 0, responseStatus: undefined }),
    entry(url, { encodedBodySize: 0, responseStatus: 404, secureConnectionStart: NaN })]);
  const result = f.collect();
  assert.equal(result.entries.length, 2);
  assert.equal(result.entries[0].transferSize, 0); assert.equal(result.entries[0].responseStart, 0);
  assert.equal(result.entries[0].responseStatus, null); assert.equal(result.entries[1].responseStatus, 404);
  assert.equal(result.entries[1].secureConnectionStart, null); assert.equal(result.entries[0].method, undefined);
});

test('bounded buffer and output truncation are explicit; post-grade completions are excluded', () => {
  const f = fixture([entry('/__tess_cache/a.tess'), entry('/__tess_cache/b.tess'),
    entry('/__tess_cache/c.tess', { responseEnd: 251 })]);
  f.context.window.__cadResourceTimingProbe.maxReportedEntries = 1;
  let result = f.collect();
  assert.equal(result.entries.length, 1); assert.equal(result.matchingEntries, 2);
  assert.equal(result.afterCutoffEntries, 1); assert.equal(result.truncated, true);
  f.context.window.__cadResourceTimingProbe.maxReportedEntries = 10;
  f.full(); result = f.collect();
  assert.equal(result.bufferFullEvents, 1); assert.equal(result.truncated, true);
});
