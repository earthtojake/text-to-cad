import assert from 'node:assert/strict';
import { test } from 'node:test';
import vm from 'node:vm';
import { installWorkerProbe } from './worker-probe.mjs';

test('the probe counts live workers, and a worker terminated twice once', () => {
  let nativeTerminations = 0;
  const window = { Worker: class { terminate() { nativeTerminations += 1; } } };
  vm.runInNewContext(`(${installWorkerProbe.toString()})()`, { window });
  const first = new window.Worker();
  new window.Worker();
  first.terminate();
  first.terminate();
  assert.deepEqual({ ...window.__cadWorkerProbe }, { created: 2, terminated: 1, live: 1, peakLive: 2 });
  assert.equal(nativeTerminations, 2, 'each call still reaches the worker');
});
