import assert from "node:assert/strict";
import test from "node:test";
import { deleteShare, SHARE_GONE, shareApiUrl, sharePromptSubject, shareService } from "./share.js";

const ID = "AbCdEfGhIjKlMnOpQrSt_-";
const PACK = "d61037e21c7e5fc5318069739439f61ccea49f6b11a1dad1ecf15cb0d831e680";
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

test("a share's manifest is read at its API on the page's own origin, never cached, and a 404 says it is gone", async () => {
  assert.equal(shareApiUrl(ID, ORIGIN), `${ORIGIN}/v1/shares/${ID}`);
  const found = service(200, new Uint8Array([1, 2, 3]));
  assert.deepEqual(new Uint8Array(await shareService(ID, { fetch: found.fetch, origin: ORIGIN }).manifest()), new Uint8Array([1, 2, 3]));
  const [asked] = found.asked;
  assert.equal(asked.url, `${ORIGIN}/v1/shares/${ID}`);
  assert.equal(asked.cache, "no-store");
  assert.equal(asked.credentials, "omit");
  assert.equal(asked.headers, undefined);
  await assert.rejects(shareService(ID, { fetch: service(404).fetch, origin: ORIGIN }).manifest(), error => error.code === SHARE_GONE);
  await assert.rejects(shareService(ID, { fetch: service(429, JSON.stringify({ error: "Too many requests.", hint: "Wait." })).fetch, origin: ORIGIN }).manifest(),
    error => error.status === 429 && error.code === undefined && /Too many requests/.test(error.message));
});

test("a share's pack is read beside its manifest, as the browser's cache keeps it, and its refusals keep their status", async () => {
  const found = service(200, new Uint8Array([4, 5]));
  const controller = new AbortController();
  assert.deepEqual(new Uint8Array(await shareService(ID, { fetch: found.fetch, origin: ORIGIN }).pack(PACK, { signal: controller.signal })),
    new Uint8Array([4, 5]));
  const [asked] = found.asked;
  assert.equal(asked.url, `${ORIGIN}/v1/shares/${ID}/packs/${PACK}`);
  assert.equal(asked.cache, undefined);
  assert.equal(asked.credentials, "omit");
  assert.equal(asked.signal, controller.signal);
  assert.equal(asked.headers, undefined);
  // A pack the service has none of is no share gone: the share may have been shared again since its manifest was read.
  await assert.rejects(shareService(ID, { fetch: service(404, JSON.stringify({ error: "No such pack." })).fetch, origin: ORIGIN }).pack(PACK),
    error => error.status === 404 && error.code === undefined && /No such pack/.test(error.message));
});

test("a prompt from a share's view names the model by the share's link, and tells the agent how to get its files", () => {
  assert.deepEqual(sharePromptSubject(ID, ORIGIN), {
    resource: { kind: "url", url: `${ORIGIN}/${ID}` },
    note: `This model is shared at ${ORIGIN}/${ID}: run \`cad fork ${ORIGIN}/${ID}\` to get its files, then work on them.`,
  });
  // Any origin the page is served from, a local one's port included.
  assert.equal(sharePromptSubject(ID, "http://127.0.0.1:8787").resource.url, `http://127.0.0.1:8787/${ID}`);
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
