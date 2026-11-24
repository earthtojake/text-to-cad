import assert from "node:assert/strict";
import test from "node:test";
import { deleteShare, fetchShare, SHARE_GONE, shareApiUrl } from "./share.js";

const ID = "AbCdEfGhIjKlMnOpQrSt_-";
const SECRET = "s".repeat(43);
const ORIGIN = "https://share.example";

/** A stand-in for the service: what it was asked, and the answer it gives. */
function service(status, body = null) {
  const asked = [];
  const fetch = async (url, init = {}) => {
    asked.push({ url, ...init });
    return new Response(body, { status, headers: body && typeof body === "string" ? { "content-type": "application/json" } : {} });
  };
  return { fetch, asked };
}

test("a share's bytes are read at its API on the page's own origin, and a 404 says it is gone", async () => {
  assert.equal(shareApiUrl(ID, ORIGIN), `${ORIGIN}/v1/shares/${ID}`);
  const found = service(200, new Uint8Array([1, 2, 3]));
  assert.deepEqual(new Uint8Array(await fetchShare(ID, { fetch: found.fetch, origin: ORIGIN })), new Uint8Array([1, 2, 3]));
  assert.equal(found.asked[0].url, `${ORIGIN}/v1/shares/${ID}`);
  assert.equal(found.asked[0].credentials, "omit");
  assert.equal(found.asked[0].headers, undefined);
  await assert.rejects(fetchShare(ID, { fetch: service(404).fetch, origin: ORIGIN }), error => error.code === SHARE_GONE);
  await assert.rejects(fetchShare(ID, { fetch: service(429, JSON.stringify({ error: "Too many requests.", hint: "Wait." })).fetch, origin: ORIGIN }),
    error => error.status === 429 && error.code === undefined && /Too many requests/.test(error.message));
});

test("a deletion sends the secret as its Authorization alone, and reads 204, 404 and 403 as their outcomes", async () => {
  const deleted = service(204);
  assert.equal(await deleteShare(ID, SECRET, { fetch: deleted.fetch, origin: ORIGIN }), "deleted");
  const [request] = deleted.asked;
  assert.equal(request.method, "DELETE");
  assert.equal(request.url, `${ORIGIN}/v1/shares/${ID}`);
  assert.deepEqual(request.headers, { Authorization: `Bearer ${SECRET}` });
  assert.equal(await deleteShare(ID, SECRET, { fetch: service(404).fetch, origin: ORIGIN }), "gone");
  assert.equal(await deleteShare(ID, SECRET, { fetch: service(403).fetch, origin: ORIGIN }), "refused");
  await assert.rejects(deleteShare(ID, SECRET, { fetch: service(500).fetch, origin: ORIGIN }),
    error => error.status === 500 && !error.message.includes(SECRET));
});
