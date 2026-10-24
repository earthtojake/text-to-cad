import assert from 'node:assert/strict';
import { test } from 'node:test';
import { clientOf, FORGET_LIMIT, rateLimiter } from './limit.mjs';

const clock = (at = 0) => { const now = () => at; now.advance = ms => { at += ms; }; return now; };

test('a key may ask five times in ten minutes; the sixth is refused with the seconds to wait, another key is not', () => {
  assert.deepEqual(FORGET_LIMIT, { limit: 5, windowMs: 600_000, size: 1000 });
  const now = clock();
  const limiter = rateLimiter({ now });
  for (let i = 0; i < 5; i += 1) { assert.deepEqual(limiter.take('a'), { ok: true }); now.advance(1000); }
  assert.deepEqual(limiter.take('a'), { ok: false, retryAfter: 595 });
  assert.deepEqual(limiter.take('b'), { ok: true });
  // A refusal counts nothing: once the first request leaves the window, one more is taken.
  now.advance(595_000);
  assert.deepEqual(limiter.take('a'), { ok: true });
  assert.equal(limiter.take('a').ok, false);
});

test('the map keeps at most its size, the oldest key evicted first', () => {
  const limiter = rateLimiter({ limit: 1, size: 3, now: clock() });
  for (const key of ['a', 'b', 'c', 'd']) limiter.take(key);
  assert.equal(limiter.size, 3);
  assert.equal(limiter.take('a').ok, true); // evicted, so counted afresh
  assert.equal(limiter.take('d').ok, false); // kept
  assert.equal(limiter.size, 3);
});

test("the client is Vercel's forwarded address, else x-forwarded-for's first hop, else none", () => {
  assert.equal(clientOf(new Headers({ 'x-vercel-forwarded-for': '203.0.113.7', 'x-forwarded-for': '198.51.100.1' })), '203.0.113.7');
  assert.equal(clientOf(new Headers({ 'x-forwarded-for': '198.51.100.1, 10.0.0.1' })), '198.51.100.1');
  assert.equal(clientOf(new Headers()), null);
});
