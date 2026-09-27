import assert from 'node:assert/strict';
import test from 'node:test';
import { createCadClient } from './client.js';
import { encodeComponentTessellation, tessellationCacheKey } from '../lib/surf/tessellationCache.js';

const surfaceInput = '11'.repeat(32);
const surfaceObject = 'aa'.repeat(32);
const bytes = encodeComponentTessellation({
  positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
  normals: new Float32Array([0, 0, 1, 0, 0, 1, 0, 0, 1]),
  faceOrds: new Float32Array([1, 1, 1]),
  indices: new Uint32Array([0, 1, 2]),
  sideOrds: new Uint32Array([1, 2, 3]),
  faceRanges: [{ ord: 1, color: null, indexStart: 0, indexCount: 3 }],
  edges: [], bounds: { min: [0, 0, 0], max: [1, 1, 0] }, scale: 1,
}, { surfaceInput, surfaceObject, edgeClasses: [] });

test('a root client carries cache writes across render sessions and cancels them only at root disposal', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const writes = [];
  let holdWrite = false;
  const client = createCadClient({ origin: 'http://root-cache.test', fetch: async (url, options) => {
    writes.push({ url, options });
    if (!holdWrite) return new Response('', { status: 200 });
    return new Promise((_resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
    });
  } });
  try {
    const previous = client.createRenderSession({ file: 'previous.step' });
    await previous.tessellationCache.writeBackEntryBytes(surfaceInput, {}, bytes);
    previous.dispose();
    const reopened = client.createRenderSession({ file: 'reopened.step' });
    assert.equal(writes.length, 0, 'construction and borrowing remain inert; writes wait for the quiet drain');
    assert.equal(reopened.tessellationCache.memoryStats().pendingWriteBackBytes, bytes.byteLength);
    await reopened.tessellationCache.flushTessellationCacheWriteBacks();
    assert.equal(writes.length, 1, 'the new render session flushes the root queue left by the previous view');
    assert.equal(writes[0].url, `http://root-cache.test/__tess_cache/${tessellationCacheKey(surfaceInput)}.tess`);
    assert.equal(writes[0].options.headers['x-cadgen-viewer'], '1');
    assert.equal(writes[0].options.body, bytes);
    assert.equal(previous.signal.aborted, true);
    assert.equal(writes[0].options.signal.aborted, false, 'the provider does not inherit the retired view signal');

    holdWrite = true;
    await reopened.tessellationCache.writeBackEntryBytes(surfaceInput, {}, bytes);
    const drain = reopened.tessellationCache.flushTessellationCacheWriteBacks();
    assert.equal(writes.length, 2);
    const activeWrite = writes[1].options.signal;
    assert.equal(activeWrite.aborted, false);
    client.dispose();
    assert.equal(activeWrite.aborted, true, 'the root still owns cancellation of an active HTTP write');
    assert.equal(reopened.signal.aborted, true);
    await drain;
    assert.equal(reopened.tessellationCache.memoryStats().writeBackBytes, 0);
    assert.throws(() => client.createRenderSession(), /disposed/);
  } finally {
    client.dispose();
  }
});
