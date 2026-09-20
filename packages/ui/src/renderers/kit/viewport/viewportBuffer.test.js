import assert from 'node:assert/strict';
import test from 'node:test';
import { createViewportBuffer } from './viewportBuffer.js';

test('a held frame survives queued DPR/viewport changes until its replacement draw', () => {
  const calls = [];
  const buffer = createViewportBuffer({
    setDrawingBufferSize: (...args) => calls.push(args),
  }, { width: 400, height: 300, pixelRatio: 2 });
  buffer.request({ pixelRatio: 1 });
  buffer.request({ width: 500, height: 350 });
  assert.deepEqual(calls, [], 'preparation must not clear the displayed canvas');
  assert.equal(buffer.flush(), true);
  assert.deepEqual(calls, [[500, 350, 1]]);
  assert.equal(buffer.flush(), false, 'unchanged buffers are never cleared');
  buffer.request({ pixelRatio: 2 });
  buffer.request({ pixelRatio: 1 });
  assert.equal(buffer.flush(), false, 'superseded quality changes coalesce away');
});
