import assert from 'node:assert/strict';
import test from 'node:test';
import { createStudioEnvironmentCache } from './studioEnvironmentCache.js';

function workers(t) {
  const all = [];
  class Worker {
    constructor() { all.push(this); }
    postMessage() {}
    terminate() { this.closed = true; }
    finish() { this.onmessage({ data: { data: new Uint16Array(16), width: 2, height: 2 } }); }
  }
  const before = { Worker: globalThis.Worker, OffscreenCanvas: globalThis.OffscreenCanvas };
  Object.assign(globalThis, { Worker, OffscreenCanvas: class {} });
  t.after(() => { for (const [key, value] of Object.entries(before)) value === undefined ? delete globalThis[key] : globalThis[key] = value; });
  return all;
}
const studio = { environmentResourceIdentity: configuration => configuration.key };

test('worker maps are reused, bounded and release GPU textures on eviction/dispose', async t => {
  const all = workers(t), cache = createStudioEnvironmentCache({ maxEntries: 2 });
  async function prepare(key, pinned) {
    const pending = cache.prepare(studio, {}, { key }, 256, new AbortController().signal, pinned);
    all.at(-1).finish(); return pending;
  }
  const a = await prepare('a'); let aDisposed=0; a.texture.addEventListener('dispose', () => aDisposed++);
  assert.equal(await cache.prepare(studio, {}, { key: 'a' }, 256), a);
  assert.equal(all.length, 1);
  const b = await prepare('b'); let bDisposed=0; b.texture.addEventListener('dispose', () => bDisposed++);
  await prepare('c', a);
  assert.equal(aDisposed, 0); assert.equal(bDisposed, 1);
  assert.equal(cache.get('b'), undefined); assert.equal(cache.owns(a), true);
  cache.dispose(); assert.equal(aDisposed, 1); assert.equal(all[0].closed, true);
});

test('superseding an environment terminates only pending work and permits a new request', async t => {
  const all = workers(t), cache = createStudioEnvironmentCache(), abort = new AbortController();
  const pending = cache.prepare(studio, {}, { key: 'a' }, 256, abort.signal);
  abort.abort(); await assert.rejects(pending, { name: 'AbortError' });
  assert.equal(all[0].closed, true);
  const next = cache.prepare(studio, {}, { key: 'b' }, 512);
  all[1].finish(); assert.equal((await next).identity, 'b');
  cache.dispose();
});
