import assert from 'node:assert/strict';
import test from 'node:test';
import { createCadClient } from './client.js';
import { tessellationCacheKey } from '../lib/surf/tessellationCache.js';

const surfaceInput = '11'.repeat(32);
const tessellation = { chordTolerance: 2e-3, angleTolerance: 0.5 };

test('render sessions borrow the root client\'s mesh store: a view cancels its own reads, the root every read', async () => {
  const requests = [];
  const client = createCadClient({ origin: 'http://root-cache.test', fetch: async (url, options) => {
    requests.push({ url, options });
    return new Promise((resolve, reject) => {
      options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true });
      requests.at(-1).answer = () => resolve(new Response(JSON.stringify({ entries: {} }), { status: 200 }));
    });
  } });
  try {
    const previous = client.createRenderSession({ file: 'previous.step' });
    const reopened = client.createRenderSession({ file: 'reopened.step' });
    const oldRead = previous.tessellationCache.probeCachedTessellationEntries([surfaceInput], tessellation);
    const currentRead = reopened.tessellationCache.probeCachedTessellationEntries([surfaceInput], tessellation);
    assert.equal(requests.length, 2);
    for (const { url, options } of requests) {
      assert.equal(url, 'http://root-cache.test/__tess_cache/probe');
      assert.equal(options.headers['x-cadgen-viewer'], '1');
      assert.deepEqual(JSON.parse(options.body), { tessellationInputs: [tessellationCacheKey(surfaceInput, tessellation)] });
    }
    previous.dispose();
    assert.equal(previous.signal.aborted, true);
    await assert.rejects(oldRead, { name: 'AbortError' });
    assert.equal(requests[1].options.signal.aborted, false, 'another view keeps its own read');
    requests[1].answer();
    assert.equal((await currentRead).size, 0);

    const lastRead = reopened.tessellationCache.probeCachedTessellationEntries([surfaceInput], tessellation);
    const activeRead = requests[2].options.signal;
    client.dispose();
    assert.equal(activeRead.aborted, true, 'the root owns cancellation of every read');
    assert.equal(reopened.signal.aborted, true);
    await assert.rejects(lastRead, { name: 'AbortError' });
    assert.throws(() => client.createRenderSession(), /disposed/);
  } finally {
    client.dispose();
  }
});
