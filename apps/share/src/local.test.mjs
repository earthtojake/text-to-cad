// The local runner (serve.mjs) serves the real Worker the way the deployment does: started as a
// command, over HTTP, its stand-ins honouring what the Worker asks of R2, the static assets and the
// routing wrangler.jsonc configures.

import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, randomBytes, webcrypto } from "node:crypto";
import { mkdtempSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createInterface } from "node:readline";
import { after, describe, test } from "node:test";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

import { APP_ROOT, LocalBucket, readConfig, runsWorkerFirst } from "./local.mjs";

const SERVE = fileURLToPath(new URL("../serve.mjs", import.meta.url));
const root = mkdtempSync(join(tmpdir(), "share-local-"));
after(() => rmSync(root, { recursive: true, force: true }));

const assetsDir = join(root, "viewer");
mkdirSync(join(assetsDir, "assets"), { recursive: true });
writeFileSync(join(assetsDir, "index.html"), "<!doctype html><html><head><script>1</script></head><body>viewer</body></html>");
writeFileSync(join(assetsDir, "assets", "app.js"), "export {};\n");

const b64url = (bytes) => Buffer.from(bytes).toString("base64url");
const sha256 = (text) => createHash("sha256").update(text).digest("hex");

/** Start serve.mjs and wait for the one line it prints when ready. */
function start(...args) {
  const child = spawn(process.execPath, [SERVE, ...args], { stdio: ["ignore", "pipe", "pipe"] });
  let errors = "";
  child.stderr.on("data", (chunk) => { errors += chunk; });
  const reader = createInterface({ input: child.stdout });
  const printed = [];
  const ready = new Promise((resolve, reject) => {
    reader.on("line", (line) => { printed.push(line); if (printed.length === 1) resolve(line); });
    child.once("exit", (code) => reject(new Error(`serve.mjs exited ${code}: ${errors}`)));
  });
  const closed = new Promise((resolve) => reader.once("close", resolve));
  const exited = new Promise((resolve) => child.once("exit", resolve));
  return {
    origin: ready,
    /** Stop it; resolves to every line it printed. */
    stop: async () => { child.kill("SIGTERM"); await Promise.all([exited, closed]); return printed; },
  };
}

function newShare() {
  return { id: b64url(randomBytes(16)), key: b64url(randomBytes(32)), write: b64url(randomBytes(32)), delete: b64url(randomBytes(32)) };
}

function upload(origin, share, body) {
  return fetch(`${origin}/v1/shares/${share.id}`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${share.write}`, "Cad-Share-Key": share.key, "Cad-Delete-Hash": sha256(share.delete) },
    body,
  });
}

async function decrypt(key, stored) {
  const bytes = new Uint8Array(stored);
  const imported = await webcrypto.subtle.importKey("raw", Buffer.from(key, "base64url"), "AES-GCM", false, ["decrypt"]);
  return Buffer.from(await webcrypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12) }, imported, bytes.slice(12)));
}

describe("serve.mjs", () => {
  test("prints its origin on one line and serves the Worker: upload, read, page, files, delete", async () => {
    const server = start("--port", "0", "--assets", assetsDir);
    try {
      const origin = await server.origin;
      assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);

      const share = newShare();
      const body = gzipSync(Buffer.from("bundle"));
      const made = await upload(origin, share, body);
      assert.equal(made.status, 201);
      const read = await fetch(`${origin}/v1/shares/${share.id}`);
      assert.equal(read.status, 200);
      assert.deepEqual(await decrypt(share.key, await read.arrayBuffer()), body);

      const page = await fetch(`${origin}/${share.id}`);
      assert.equal(page.status, 200);
      assert.match(page.headers.get("Content-Security-Policy"), /frame-ancestors 'none'/);
      assert.match(await page.text(), /viewer/);

      // A file is served by the assets alone (asset-first), but HTML, which the Worker answers.
      const script = await fetch(`${origin}/assets/app.js`);
      assert.equal(script.status, 200);
      assert.equal(script.headers.get("X-Content-Type-Options"), null);
      const index = await fetch(`${origin}/index.html`);
      assert.match(index.headers.get("Content-Security-Policy"), /script-src/);

      const home = await fetch(`${origin}/`, { redirect: "manual" });
      assert.equal(home.status, 302);
      assert.equal(home.headers.get("Location"), "https://www.texttocad.dev");

      const streamed = await fetch(`${origin}/v1/shares/${share.id}`, {
        method: "PUT",
        duplex: "half",
        headers: { Authorization: `Bearer ${share.write}`, "Cad-Share-Key": share.key, "Cad-Delete-Hash": sha256(share.delete) },
        body: new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(body)); controller.close(); } }),
      });
      assert.equal(streamed.status, 411);

      const deleted = await fetch(`${origin}/v1/shares/${share.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${share.delete}` } });
      assert.equal(deleted.status, 204);
      assert.equal((await fetch(`${origin}/v1/shares/${share.id}`)).status, 404);
      assert.deepEqual(await server.stop(), [origin], "it prints its origin and nothing else");
    } finally {
      await server.stop();
    }
  });

  test("with --store keeps shares across a restart, encrypted, without the key", async () => {
    const store = join(root, "store");
    const share = newShare();
    const body = gzipSync(Buffer.from("kept"));
    const first = start("--port", "0", "--assets", assetsDir, "--store", store);
    try {
      assert.equal((await upload(await first.origin, share, body)).status, 201);
    } finally {
      await first.stop();
    }
    const files = readdirSync(store);
    assert.ok(files.length > 0);
    for (const name of files) {
      const kept = readFileSync(join(store, name));
      for (const value of [share.key, share.write, share.delete]) assert.ok(!kept.includes(value), name);
      assert.ok(!kept.includes(Buffer.from(share.key, "base64url")), name);
    }
    const second = start("--port", "0", "--assets", assetsDir, "--store", store);
    try {
      const read = await fetch(`${await second.origin}/v1/shares/${share.id}`);
      assert.equal(read.status, 200);
      assert.deepEqual(await decrypt(share.key, await read.arrayBuffer()), body);
    } finally {
      await second.stop();
    }
  });

  test("refuses to start without its port or its assets folder", async () => {
    for (const args of [["--assets", assetsDir], ["--port", "0"], ["--port", "0", "--assets", join(root, "absent")]]) {
      const child = spawn(process.execPath, [SERVE, ...args], { stdio: "ignore" });
      assert.equal(await new Promise((resolve) => child.once("exit", resolve)), 2);
    }
  });
});

describe("the stand-ins", () => {
  test("the bucket's put honours onlyIf as R2 does: If-None-Match * creates only, etagMatches replaces only", async () => {
    const bucket = new LocalBucket();
    const absent = new Headers({ "If-None-Match": "*" });
    const made = await bucket.put("k", new Uint8Array([1]), { onlyIf: absent, customMetadata: { a: "1" } });
    assert.ok(made);
    assert.equal(await bucket.put("k", new Uint8Array([2]), { onlyIf: absent }), null);
    assert.equal(await bucket.put("k", new Uint8Array([2]), { onlyIf: { etagMatches: "other" } }), null);
    const replaced = await bucket.put("k", new Uint8Array([3]), { onlyIf: { etagMatches: made.etag } });
    assert.ok(replaced);
    const object = await bucket.get("k");
    assert.deepEqual(new Uint8Array(await object.arrayBuffer()), new Uint8Array([3]));
    assert.deepEqual(object.customMetadata, {});
    assert.equal((await bucket.head("k")).size, 1);
    await bucket.delete("k");
    assert.equal(await bucket.head("k"), null);
    assert.equal(await bucket.get("k"), null);
    assert.equal(await bucket.put("k", new Uint8Array([4]), { onlyIf: { etagMatches: made.etag } }), null);
  });

  test("the routing follows wrangler.jsonc: the Worker first for the API and HTML, asset-first for the rest", async () => {
    const config = await readConfig(join(APP_ROOT, "wrangler.jsonc"));
    assert.equal(config.main, "src/worker.mjs");
    assert.deepEqual(config.r2_buckets.map((bucket) => bucket.binding), ["SHARES"]);
    assert.deepEqual(config.ratelimits.map((limiter) => limiter.name), ["LIMITER"]);
    assert.equal(config.assets.binding, "ASSETS");
    assert.equal(config.assets.directory, "./viewer");
    assert.deepEqual(Object.keys(config.vars).sort(), ["EXPIRY_DAYS", "MAX_SHARE_BYTES"]);
    const first = config.assets.run_worker_first;
    for (const path of ["/v1/shares/abc", "/index.html", "/deep/page.html"]) assert.ok(runsWorkerFirst(first, path), path);
    for (const path of ["/", "/assets/app.js", "/AAAAAAAAAAAAAAAAAAAAAA"]) assert.ok(!runsWorkerFirst(first, path), path);
    assert.ok(!runsWorkerFirst(["/v1/*", "!/v1/open/*"], "/v1/open/x"));
    assert.ok(runsWorkerFirst(true, "/anything"));
  });
});
