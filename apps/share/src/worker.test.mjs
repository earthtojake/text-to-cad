// The Worker's contract (README.md), run on the real module with the local stand-ins for its
// bindings and a clock of the test's own.

import assert from "node:assert/strict";
import { createHash, randomBytes, webcrypto } from "node:crypto";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, test } from "node:test";
import { gzipSync } from "node:zlib";

import { LocalBucket, allowAll, localAssets } from "./local.mjs";
import { DEFAULT_MAX_SHARE_BYTES, FORMAT, HOME, handle } from "./worker.mjs";

const DAY = 24 * 60 * 60 * 1000;
const START = Date.parse("2026-03-01T12:00:00.000Z");
const ORIGIN = "https://share.test";
const ADDRESS = "203.0.113.7";

const INLINE = "globalThis.__boot = 1;";
const INDEX = `<!doctype html><html><head><script>${INLINE}</script>` +
  `<script type="module" src="./assets/app.js"></script></head><body></body></html>`;
const assetsDir = mkdtempSync(join(tmpdir(), "share-assets-"));
writeFileSync(join(assetsDir, "index.html"), INDEX);
mkdirSync(join(assetsDir, "assets"));
writeFileSync(join(assetsDir, "assets", "app.js"), "export {};\n");
after(() => rmSync(assetsDir, { recursive: true, force: true }));

const b64url = (bytes) => Buffer.from(bytes).toString("base64url");
const sha256 = (text) => createHash("sha256").update(text).digest("hex");

function newShare() {
  return {
    id: b64url(randomBytes(16)),
    key: b64url(randomBytes(32)),
    write: b64url(randomBytes(32)),
    delete: b64url(randomBytes(32)),
  };
}

function archive(text = "a view bundle's files") {
  return new Uint8Array(gzipSync(Buffer.from(text)));
}

function environment({ limiter = allowAll, ...vars } = {}) {
  return { SHARES: new LocalBucket(), ASSETS: localAssets(assetsDir), LIMITER: limiter, ...vars };
}

function clock(at = START) {
  const time = { at };
  return { time, now: () => time.at };
}

async function call(env, method, path, { headers = {}, body, now = () => START } = {}) {
  const request = new Request(`${ORIGIN}${path}`, {
    method,
    headers: { "CF-Connecting-IP": ADDRESS, ...headers },
    body,
    duplex: body instanceof ReadableStream ? "half" : undefined,
  });
  return handle(request, env, { now });
}

function upload(env, share, body = archive(), { headers = {}, now } = {}) {
  return call(env, "PUT", `/v1/shares/${share.id}`, {
    now,
    body,
    headers: {
      Authorization: `Bearer ${share.write}`,
      "Cad-Share-Key": share.key,
      "Cad-Delete-Hash": sha256(share.delete),
      "Content-Length": String(body.byteLength),
      ...headers,
    },
  });
}

async function decrypt(key, stored) {
  const bytes = new Uint8Array(stored);
  const imported = await webcrypto.subtle.importKey("raw", Buffer.from(key, "base64url"), "AES-GCM", false, ["decrypt"]);
  return new Uint8Array(await webcrypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12) }, imported, bytes.slice(12)));
}

async function refusal(response, status, error) {
  assert.equal(response.status, status);
  assert.match(response.headers.get("Content-Type"), /^application\/json/);
  const body = await response.json();
  assert.equal(body.error, error);
  assert.equal(typeof body.hint, "string");
  assert.ok(body.hint.length > 0);
  return body;
}

describe("an upload", () => {
  test("makes a share: 201 with its id, expiry and stored size, and the stored bytes decrypt to the archive", async () => {
    const env = environment();
    const share = newShare();
    const body = archive();
    const made = await upload(env, share, body);
    assert.equal(made.status, 201);
    const answer = await made.json();
    assert.deepEqual(answer, { id: share.id, expires: new Date(START + 7 * DAY).toISOString(), bytes: body.byteLength + 28 });

    const read = await call(env, "GET", `/v1/shares/${share.id}`);
    assert.equal(read.status, 200);
    assert.equal(read.headers.get("Content-Type"), "application/octet-stream");
    assert.equal(read.headers.get("Cache-Control"), "no-store");
    assert.equal(read.headers.get("Cad-Share-Expires"), answer.expires);
    const stored = await read.arrayBuffer();
    assert.equal(stored.byteLength, answer.bytes);
    assert.deepEqual(await decrypt(share.key, stored), body);
  });

  test("keeps neither the key nor a secret: only the format, the two hashes and the expiry beside the ciphertext", async () => {
    const env = environment();
    const share = newShare();
    const body = archive();
    assert.equal((await upload(env, share, body)).status, 201);
    const object = await env.SHARES.get(share.id);
    assert.deepEqual(object.customMetadata, {
      format: FORMAT,
      write: sha256(share.write),
      delete: sha256(share.delete),
      expires: new Date(START + 7 * DAY).toISOString(),
    });
    const stored = Buffer.from(await object.arrayBuffer());
    const kept = JSON.stringify(await env.SHARES.head(share.id)) + stored.toString("latin1");
    for (const value of [share.key, share.write, share.delete]) assert.ok(!kept.includes(value));
    assert.ok(!stored.includes(Buffer.from(share.key, "base64url")));
    assert.ok(!stored.includes(Buffer.from(body)), "the archive is not kept in the clear");
  });

  test("again with the write secret replaces it: 200, a fresh IV, the 7 days start again", async () => {
    const env = environment();
    const share = newShare();
    const { time, now } = clock();
    assert.equal((await upload(env, share, archive("first"), { now })).status, 201);
    const first = new Uint8Array(await (await env.SHARES.get(share.id)).arrayBuffer());

    time.at += 3 * DAY;
    const again = await upload(env, share, archive("second"), { now });
    assert.equal(again.status, 200);
    assert.equal((await again.json()).expires, new Date(time.at + 7 * DAY).toISOString());
    const stored = await (await call(env, "GET", `/v1/shares/${share.id}`, { now })).arrayBuffer();
    assert.deepEqual(await decrypt(share.key, stored), archive("second"));
    assert.notDeepEqual(new Uint8Array(stored).slice(0, 12), first.slice(0, 12));

    time.at += 6 * DAY; // past the first upload's 7 days, within the second's
    assert.equal((await call(env, "GET", `/v1/shares/${share.id}`, { now })).status, 200);
  });

  test("again with another write secret is refused (403) and leaves the share as it was", async () => {
    const env = environment();
    const share = newShare();
    assert.equal((await upload(env, share, archive("mine"))).status, 201);
    const other = { ...newShare(), id: share.id };
    await refusal(await upload(env, other, archive("theirs")), 403, "forbidden");
    const stored = await (await call(env, "GET", `/v1/shares/${share.id}`)).arrayBuffer();
    assert.deepEqual(await decrypt(share.key, stored), archive("mine"));
  });

  test("two creates of one id at once: one makes it, the other is judged against it", async () => {
    const env = environment();
    const one = newShare();
    const two = { ...newShare(), id: one.id };
    const statuses = (await Promise.all([upload(env, one), upload(env, two)])).map((response) => response.status);
    assert.deepEqual(statuses.sort(), [201, 403]);
  });

  test("of an id whose share expired makes a new share, whoever uploads", async () => {
    const env = environment();
    const share = newShare();
    const { time, now } = clock();
    assert.equal((await upload(env, share, archive(), { now })).status, 201);
    time.at += 7 * DAY + 1;
    const other = { ...newShare(), id: share.id };
    assert.equal((await upload(env, other, archive("new"), { now })).status, 201);
  });

  test("refuses what the protocol refuses, each with its status", async () => {
    const env = environment();
    const share = newShare();
    const body = archive();
    await refusal(await upload(env, { ...share, id: "short" }), 400, "bad_id");
    await refusal(await upload(env, { ...share, id: `${share.id}=` }), 400, "bad_id");
    await refusal(await upload(env, share, body, { headers: { Authorization: "" } }), 401, "unauthorized");
    await refusal(await upload(env, share, body, { headers: { Authorization: `Basic ${share.write}` } }), 401, "unauthorized");
    await refusal(await upload(env, share, body, { headers: { Authorization: "Bearer short" } }), 401, "unauthorized");
    await refusal(await upload(env, share, body, { headers: { "Cad-Share-Key": "" } }), 400, "bad_key");
    await refusal(await upload(env, share, body, { headers: { "Cad-Share-Key": b64url(randomBytes(16)) } }), 400, "bad_key");
    await refusal(await upload(env, share, body, { headers: { "Cad-Share-Key": `${share.key.slice(1)}+` } }), 400, "bad_key");
    await refusal(await upload(env, share, body, { headers: { "Cad-Delete-Hash": sha256(share.delete).toUpperCase() } }), 400, "bad_delete_hash");
    await refusal(await upload(env, share, body, { headers: { "Cad-Delete-Hash": share.delete } }), 400, "bad_delete_hash");
    await refusal(await upload(env, share, new Uint8Array(Buffer.from("plain text, not gzip"))), 400, "not_gzip");
    await refusal(await upload(env, share, new Uint8Array(0)), 400, "not_gzip");
    const unauthorized = await upload(env, share, body, { headers: { Authorization: "" } });
    assert.equal(unauthorized.headers.get("WWW-Authenticate"), "Bearer");
    assert.deepEqual(await env.SHARES.keys(), []);
  });

  test("without a Content-Length is refused (411)", async () => {
    const env = environment();
    const share = newShare();
    const stream = new ReadableStream({ start(controller) { controller.enqueue(archive()); controller.close(); } });
    const response = await call(env, "PUT", `/v1/shares/${share.id}`, {
      body: stream,
      headers: { Authorization: `Bearer ${share.write}`, "Cad-Share-Key": share.key, "Cad-Delete-Hash": sha256(share.delete) },
    });
    await refusal(response, 411, "length_required");
  });

  test("over MAX_SHARE_BYTES is refused (413), whether its length says so or its body runs past it", async () => {
    const env = environment({ MAX_SHARE_BYTES: "64" });
    const share = newShare();
    const big = new Uint8Array(gzipSync(randomBytes(200)));
    assert.ok(big.byteLength > 64);
    await refusal(await upload(env, share, big), 413, "too_large");
    const lying = new ReadableStream({ start(controller) { controller.enqueue(big); controller.close(); } });
    await refusal(await upload(env, share, lying, { headers: { "Content-Length": "40" } }), 413, "too_large");
    const fits = archive("x");
    assert.ok(fits.byteLength <= 64);
    assert.equal((await upload(env, share, fits)).status, 201);
    assert.equal(DEFAULT_MAX_SHARE_BYTES, 25 * 1024 * 1024);
  });

  test("keeps EXPIRY_DAYS when the deployment sets it", async () => {
    const env = environment({ EXPIRY_DAYS: "2" });
    const response = await upload(env, newShare());
    assert.equal((await response.json()).expires, new Date(START + 2 * DAY).toISOString());
  });
});

describe("the rate limit", () => {
  test("counts uploads and deletes by the client's address, and refuses past it (429, Retry-After)", async () => {
    const keys = [];
    let allow = true;
    const limiter = { async limit({ key }) { keys.push(key); return { success: allow }; } };
    const env = environment({ limiter });
    const share = newShare();
    assert.equal((await upload(env, share)).status, 201);
    assert.equal((await call(env, "GET", `/v1/shares/${share.id}`)).status, 200);
    assert.deepEqual(keys, [ADDRESS], "a read is not counted");

    allow = false;
    const refusedUpload = await upload(env, share);
    await refusal(refusedUpload, 429, "rate_limited");
    assert.match(refusedUpload.headers.get("Retry-After"), /^\d+$/);
    const refusedDelete = await call(env, "DELETE", `/v1/shares/${share.id}`, { headers: { Authorization: `Bearer ${share.delete}` } });
    await refusal(refusedDelete, 429, "rate_limited");
    assert.match(refusedDelete.headers.get("Retry-After"), /^\d+$/);
    assert.deepEqual(keys, [ADDRESS, ADDRESS, ADDRESS]);
    assert.equal((await call(env, "GET", `/v1/shares/${share.id}`)).status, 200, "nothing was deleted");
  });
});

describe("a read", () => {
  test("HEAD answers GET's headers and no body", async () => {
    const env = environment();
    const share = newShare();
    const made = await (await upload(env, share)).json();
    const head = await call(env, "HEAD", `/v1/shares/${share.id}`);
    assert.equal(head.status, 200);
    assert.equal(head.headers.get("Content-Type"), "application/octet-stream");
    assert.equal(head.headers.get("Content-Length"), String(made.bytes));
    assert.equal(head.headers.get("Cad-Share-Expires"), made.expires);
    assert.equal(head.headers.get("Cache-Control"), "no-store");
    assert.equal(head.body, null);
  });

  test("of an id with no share is 404, and a bad id 400", async () => {
    const env = environment();
    await refusal(await call(env, "GET", `/v1/shares/${newShare().id}`), 404, "not_found");
    await refusal(await call(env, "HEAD", `/v1/shares/${newShare().id}`), 404, "not_found");
    await refusal(await call(env, "GET", "/v1/shares/not-an-id"), 400, "bad_id");
    await refusal(await call(env, "GET", "/v1/shares/"), 400, "bad_id");
  });

  test("past the expiry deletes the share and answers 404", async () => {
    const env = environment();
    const share = newShare();
    const { time, now } = clock();
    await upload(env, share, archive(), { now });
    time.at += 7 * DAY - 1;
    assert.equal((await call(env, "HEAD", `/v1/shares/${share.id}`, { now })).status, 200);
    time.at += 1;
    await refusal(await call(env, "GET", `/v1/shares/${share.id}`, { now }), 404, "not_found");
    assert.deepEqual(await env.SHARES.keys(), []);
  });
});

describe("a delete", () => {
  for (const which of ["delete", "write"]) {
    test(`with the ${which} secret deletes the share (204); then there is none (404)`, async () => {
      const env = environment();
      const share = newShare();
      await upload(env, share);
      const deleted = await call(env, "DELETE", `/v1/shares/${share.id}`, { headers: { Authorization: `Bearer ${share[which]}` } });
      assert.equal(deleted.status, 204);
      assert.equal(deleted.body, null);
      await refusal(await call(env, "GET", `/v1/shares/${share.id}`), 404, "not_found");
      await refusal(await call(env, "DELETE", `/v1/shares/${share.id}`, { headers: { Authorization: `Bearer ${share[which]}` } }), 404, "not_found");
    });
  }

  test("with a secret that matches neither hash is refused (403), and without one (401)", async () => {
    const env = environment();
    const share = newShare();
    await upload(env, share);
    await refusal(await call(env, "DELETE", `/v1/shares/${share.id}`, { headers: { Authorization: `Bearer ${newShare().delete}` } }), 403, "forbidden");
    await refusal(await call(env, "DELETE", `/v1/shares/${share.id}`), 401, "unauthorized");
    await refusal(await call(env, "DELETE", "/v1/shares/bad"), 400, "bad_id");
    assert.equal((await call(env, "GET", `/v1/shares/${share.id}`)).status, 200);
  });

  test("of an expired share is 404", async () => {
    const env = environment();
    const share = newShare();
    const { time, now } = clock();
    await upload(env, share, archive(), { now });
    time.at += 8 * DAY;
    await refusal(await call(env, "DELETE", `/v1/shares/${share.id}`, { now, headers: { Authorization: `Bearer ${share.delete}` } }), 404, "not_found");
  });
});

describe("the rest of the API", () => {
  test("another method is 405 with Allow, another path 404, and nothing answers with CORS", async () => {
    const env = environment();
    const id = newShare().id;
    const options = await call(env, "OPTIONS", `/v1/shares/${id}`, {
      headers: { Origin: "https://elsewhere.test", "Access-Control-Request-Method": "PUT" },
    });
    await refusal(options, 405, "method_not_allowed");
    assert.equal(options.headers.get("Allow"), "PUT, GET, HEAD, DELETE");
    await refusal(await call(env, "POST", `/v1/shares/${id}`), 405, "method_not_allowed");
    await refusal(await call(env, "GET", "/v1/other"), 404, "not_found");
    await refusal(await call(env, "GET", "/v1"), 404, "not_found");
    const share = newShare();
    const responses = [
      options,
      await upload(env, share, archive(), { headers: { Origin: "https://elsewhere.test" } }),
      await call(env, "GET", `/v1/shares/${share.id}`, { headers: { Origin: "https://elsewhere.test" } }),
      await call(env, "GET", `/${share.id}`, { headers: { Origin: "https://elsewhere.test" } }),
    ];
    for (const response of responses) {
      for (const name of response.headers.keys()) assert.ok(!name.startsWith("access-control-"), name);
    }
  });
});

describe("the pages", () => {
  const expectedScriptHash = `'sha256-${createHash("sha256").update(INLINE).digest("base64")}'`;

  function assertPageHeaders(response) {
    assert.equal(response.headers.get("Content-Type"), "text/html; charset=utf-8");
    const policy = response.headers.get("Content-Security-Policy");
    const directives = Object.fromEntries(policy.split("; ").map((directive) => {
      const [name, ...values] = directive.split(" ");
      return [name, values];
    }));
    assert.deepEqual(directives["default-src"], ["'self'"]);
    assert.deepEqual(directives["script-src"], ["'self'", "'wasm-unsafe-eval'", expectedScriptHash]);
    assert.deepEqual(directives["connect-src"], ["'self'", "data:", "blob:"]);
    assert.deepEqual(directives["frame-ancestors"], ["'none'"]);
    assert.deepEqual(directives["base-uri"], ["'none'"]);
    assert.deepEqual(directives["form-action"], ["'none'"]);
    assert.deepEqual(directives["worker-src"], ["'self'", "blob:"]);
    assert.equal(response.headers.get("Referrer-Policy"), "no-referrer");
    assert.equal(response.headers.get("X-Content-Type-Options"), "nosniff");
  }

  test("GET / redirects (302) to the site", async () => {
    const env = environment();
    for (const method of ["GET", "HEAD"]) {
      const response = await call(env, method, "/");
      assert.equal(response.status, 302);
      assert.equal(response.headers.get("Location"), HOME);
    }
    await refusal(await call(env, "POST", "/"), 405, "method_not_allowed");
  });

  test("a share's path answers the viewer's index.html with the page's security headers, share or no share", async () => {
    const env = environment();
    const response = await call(env, "GET", `/${newShare().id}`);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), INDEX);
    assertPageHeaders(response);
    const head = await call(env, "HEAD", `/${newShare().id}`);
    assert.equal(head.status, 200);
    assert.equal(head.body, null);
    assertPageHeaders(head);
    await refusal(await call(env, "PUT", `/${newShare().id}`), 405, "method_not_allowed");
  });

  test("the viewer's own files are served, HTML with the page's headers, and anything else is 404", async () => {
    const env = environment();
    const index = await call(env, "GET", "/index.html");
    assert.equal(index.status, 200);
    assertPageHeaders(index);
    const script = await call(env, "GET", "/assets/app.js");
    assert.equal(script.status, 200);
    assert.match(script.headers.get("Content-Type"), /^text\/javascript/);
    assert.equal(script.headers.get("X-Content-Type-Options"), "nosniff");
    assert.equal(await script.text(), "export {};\n");
    const scriptHead = await call(env, "HEAD", "/assets/app.js");
    assert.equal(scriptHead.status, 200);
    assert.equal(scriptHead.body, null);
    await refusal(await call(env, "GET", "/assets/missing.js"), 404, "not_found");
    await refusal(await call(env, "GET", `/${newShare().id}/`), 404, "not_found");
    await refusal(await call(env, "GET", "/assets/%2e%2e/%2e%2e/package.json"), 404, "not_found");
  });
});
