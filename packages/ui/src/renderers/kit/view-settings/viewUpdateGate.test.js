import assert from 'node:assert/strict';
import test from 'node:test';
import { createViewUpdateGate } from './viewUpdateGate.js';

test('compile does not clear the displayed frame and readiness follows a real draw', async () => {
  const scene = {}, camera = {}, calls = [];
  const runtime = { scene, camera, renderer: { compileAsync: async (...args) => calls.push(args) }, requestRender: () => calls.push('request') };
  const gate = createViewUpdateGate(runtime);
  gate.hold(); await gate.compile();
  assert.equal(gate.held, true);
  let complete = false; const done = gate.present().then(() => { complete = true; });
  await Promise.resolve(); assert.equal(complete, false);
  assert.equal(gate.held, false); assert.deepEqual(calls, [[scene,camera], 'request']);
  gate.didDraw(); await done;
});

test('closing the canvas rejects an outstanding presentation wait', async () => {
  const gate = createViewUpdateGate({ requestRender() {} });
  const pending = gate.present(); gate.dispose();
  await assert.rejects(pending, /Viewer closed/);
});
