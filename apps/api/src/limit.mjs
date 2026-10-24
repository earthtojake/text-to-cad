/**
 * A limit on how often one caller may ask for something, kept in memory by the instance that answers (the
 * host reuses a warm one, and each instance keeps its own). /v1/forget is open to anyone and each deletion
 * spends PostHog's personal key, so it is limited per client address and per install id: a real client asks
 * once, when `cadgen telemetry off` runs, and again only while the deletion it owes has not been taken.
 * Beyond the limit, a refusal and the time to wait: nothing is queued. The host's firewall is the second
 * layer (README.md).
 *
 * A key is kept only as a salted hash, the salt the instance's own and never written anywhere, so no address
 * is held as it is; and only for as long as its window, in a map of at most `size` keys, the oldest evicted.
 */
import { createHash, randomBytes } from 'node:crypto';

export const FORGET_LIMIT = { limit: 5, windowMs: 10 * 60_000, size: 1000 };

/**
 * @param {{ limit?: number, windowMs?: number, size?: number, now?: () => number }} [options]
 * @returns {{ take(key: string): { ok: true } | { ok: false, retryAfter: number }, readonly size: number }}
 *   `take`: counts one request under `key`; refused, it counts nothing and says how many seconds to wait.
 */
export function rateLimiter({ limit = FORGET_LIMIT.limit, windowMs = FORGET_LIMIT.windowMs, size = FORGET_LIMIT.size, now = Date.now } = {}) {
  const salt = randomBytes(16);
  const seen = new Map(); // hashed key -> the times of its requests in the window, oldest first; oldest key first
  const hash = key => createHash('sha256').update(salt).update(String(key)).digest('base64url');
  return {
    take(key) {
      const at = now();
      const id = hash(key);
      const times = (seen.get(id) ?? []).filter(time => at - time < windowMs);
      seen.delete(id); // re-inserted below as the newest
      if (times.length >= limit) {
        seen.set(id, times);
        return { ok: false, retryAfter: Math.max(1, Math.ceil((times[0] + windowMs - at) / 1000)) };
      }
      times.push(at);
      seen.set(id, times);
      while (seen.size > size) seen.delete(seen.keys().next().value);
      return { ok: true };
    },
    get size() { return seen.size; },
  };
}

/**
 * The client's address as the host gives it: Vercel's own `x-vercel-forwarded-for`, else the first hop of
 * `x-forwarded-for`. Null when neither names one.
 * @param {Headers} headers
 */
export function clientOf(headers) {
  const address = (headers.get('x-vercel-forwarded-for') || headers.get('x-forwarded-for') || '').split(',')[0].trim();
  return address || null;
}
