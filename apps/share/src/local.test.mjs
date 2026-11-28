// The local runner (serve.mjs) serves the real Worker the way the deployment does: started as a
// command, over HTTP, its stand-ins honouring what the Worker asks of R2, the static assets and their
// `_headers`, and the routing wrangler.jsonc configures.

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

import { APP_ROOT, LocalBucket, localAssets, platform, readConfig, runsWorkerFirst } from "./local.mjs";
import { DEFAULTS, nameOf } from "./worker.mjs";

const SERVE = fileURLToPath(new URL("../serve.mjs", import.meta.url));
const root = mkdtempSync(join(tmpdir(), "share-local-"));
after(() => rmSync(root, { recursive: true, force: true }));

// The viewer as the deployment's assets hold it: its page, a file, and the `_headers` the build writes.
const assetsDir = join(root, "viewer");
mkdirSync(join(assetsDir, "assets"), { recursive: true });
writeFileSync(join(assetsDir, "index.html"), "<!doctype html><html><head><script>1</script></head><body>viewer</body></html>");
writeFileSync(join(assetsDir, "assets", "app.js"), "export {};\n");
writeFileSync(join(assetsDir, "_headers"), "/*\n  X-Robots-Tag: noindex, nofollow\n");

const b64url = (bytes) => Buffer.from(bytes).toString("base64url");
const sha256 = (data) => createHash("sha256").update(data).digest("hex");
const utf8 = (text) => new TextEncoder().encode(text);

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
  return { id: b64url(randomBytes(16)), write: b64url(randomBytes(32)), delete: b64url(randomBytes(32)) };
}

/** A share as the command makes one, over HTTP: one pack of the gzip members of the view's files and then of
 * the files that made it, then the commit. */
async function share(origin, who, view, code = CODE) {
  const both = [...view.map((file) => ["view", ...file]), ...code.map((file) => ["files", ...file])];
  const members = both.map(([, , content]) => gzipSync(Buffer.from(content)));
  const pack = new Uint8Array(Buffer.concat(members));
  const packId = sha256(pack);
  const entries = { view: {}, files: {} };
  let offset = 0;
  both.forEach(([map, path, content], index) => {
    entries[map][path] = { sha256: sha256(content), bytes: Buffer.byteLength(content), at: [[packId, offset, members[index].length]] };
    offset += members[index].length;
  });
  const manifest = JSON.stringify({ format: "cad-share/2", name: "juno", entry: code[0]?.[0] ?? null, made: { cad: "0.11.17" }, ...entries });
  const headers = { Authorization: `Bearer ${who.write}`, "Cad-Delete-Hash": sha256(who.delete) };
  const uploaded = await fetch(`${origin}/v1/shares/${who.id}/packs/${packId}`, { method: "PUT", headers, body: pack });
  const commit = () => fetch(`${origin}/v1/shares/${who.id}`, { method: "PUT", headers: { ...headers, "Content-Type": "application/json" }, body: manifest });
  return { pack, packId, manifest, uploaded, committed: await commit(), commit };
}

/** The key the protocol derives from an id, by this file's own HKDF. */
async function keyBytesOf(id) {
  const material = await webcrypto.subtle.importKey("raw", utf8(id), "HKDF", false, ["deriveBits"]);
  return new Uint8Array(await webcrypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: utf8("cad-share/2"), info: utf8("key") }, material, 256));
}

/** What the service sealed for the share `id`, opened under the key the id derives. */
async function unseal(id, stored, aad) {
  const key = await webcrypto.subtle.importKey("raw", await keyBytesOf(id), "AES-GCM", false, ["decrypt"]);
  const bytes = new Uint8Array(stored);
  return Buffer.from(await webcrypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12), additionalData: utf8(aad) }, key, bytes.slice(12)));
}

const BUNDLE = [["manifest.json", '{"format":"view-bundle/1"}'], ["structure.json", '{"tree":[]}']];
const CODE = [["juno.py", "print('juno')\n"]];

describe("serve.mjs", () => {
  test("prints its origin on one line and serves the Worker: a pack, a commit, the reads, the page, files, a delete", async () => {
    const server = start("--port", "0", "--assets", assetsDir);
    try {
      const origin = await server.origin;
      assert.match(origin, /^http:\/\/127\.0\.0\.1:\d+$/);

      const who = newShare();
      const { pack, packId, manifest, uploaded, committed } = await share(origin, who, BUNDLE);
      assert.equal(uploaded.status, 201);
      assert.equal(committed.status, 201);
      const read = await fetch(`${origin}/v1/shares/${who.id}`);
      assert.equal(read.status, 200);
      assert.equal(read.headers.get("X-Robots-Tag"), "noindex, nofollow");
      assert.equal((await unseal(who.id, await read.arrayBuffer(), "cad-share/2 manifest")).toString(), manifest);
      const packRead = await fetch(`${origin}/v1/shares/${who.id}/packs/${packId}`);
      assert.equal(packRead.status, 200);
      assert.match(packRead.headers.get("Cache-Control"), /\bimmutable\b/);
      assert.deepEqual(new Uint8Array(await unseal(who.id, await packRead.arrayBuffer(), `cad-share/2 pack ${packId}`)), pack);

      const page = await fetch(`${origin}/${who.id}`);
      assert.equal(page.status, 200);
      assert.match(page.headers.get("Content-Security-Policy"), /frame-ancestors 'none'/);
      assert.equal(page.headers.get("X-Robots-Tag"), "noindex, nofollow");
      assert.match(await page.text(), /viewer/);

      // The files that made it: a zip the Worker makes as it goes out, beside the page.
      const zip = await fetch(`${origin}/${who.id}.zip`);
      assert.equal(zip.status, 200);
      assert.equal(zip.headers.get("Content-Type"), "application/zip");
      assert.equal(zip.headers.get("Content-Disposition"), 'attachment; filename="juno.zip"');
      assert.equal(zip.headers.get("Cad-Share-Entry"), "juno.py");
      assert.equal(zip.headers.get("X-Robots-Tag"), "noindex, nofollow");
      const zipped = Buffer.from(await zip.arrayBuffer());
      assert.equal(zipped.readUInt32LE(0), 0x04034b50);
      assert.ok(zipped.includes("juno/juno.py") && !zipped.includes("structure.json"), "the files, and nothing of the view");
      assert.equal(zipped.readUInt32LE(zipped.length - 22), 0x06054b50);

      // A file is served by the assets alone (asset-first), with what `_headers` adds; HTML by the Worker.
      const script = await fetch(`${origin}/assets/app.js`);
      assert.equal(script.status, 200);
      assert.equal(script.headers.get("X-Content-Type-Options"), null);
      assert.equal(script.headers.get("X-Robots-Tag"), "noindex, nofollow");
      assert.equal((await fetch(`${origin}/_headers`)).status, 404);
      const index = await fetch(`${origin}/index.html`);
      assert.match(index.headers.get("Content-Security-Policy"), /script-src/);

      const home = await fetch(`${origin}/`, { redirect: "manual" });
      assert.equal(home.status, 302);
      assert.equal(home.headers.get("Location"), "https://www.texttocad.dev");

      const streamed = await fetch(`${origin}/v1/shares/${who.id}/packs/${packId}`, {
        method: "PUT",
        duplex: "half",
        headers: { Authorization: `Bearer ${who.write}`, "Cad-Delete-Hash": sha256(who.delete) },
        body: new ReadableStream({ start(controller) { controller.enqueue(pack); controller.close(); } }),
      });
      assert.equal(streamed.status, 411);

      const deleted = await fetch(`${origin}/v1/shares/${who.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${who.delete}` } });
      assert.equal(deleted.status, 204);
      assert.equal((await fetch(`${origin}/v1/shares/${who.id}`)).status, 404);
      assert.deepEqual(await server.stop(), [origin], "it prints its origin and nothing else");
    } finally {
      await server.stop();
    }
  });

  test("with --store keeps shares across a restart, sealed, without the id, the key or a secret", async () => {
    const store = join(root, "store");
    const who = newShare();
    const first = start("--port", "0", "--assets", assetsDir, "--store", store);
    let packId;
    try {
      const made = await share(await first.origin, who, BUNDLE);
      assert.equal(made.committed.status, 201);
      packId = made.packId;
    } finally {
      await first.stop();
    }
    const files = readdirSync(store);
    assert.equal(files.length, 6, "the owner, the pack and the manifest, each its bytes and its metadata");
    const bits = await keyBytesOf(who.id);
    for (const name of files) {
      const kept = readFileSync(join(store, name));
      for (const value of [who.id, who.write, who.delete, b64url(bits), Buffer.from(bits).toString("hex")]) {
        assert.ok(!kept.includes(value) && !name.includes(value), name);
      }
      assert.ok(!kept.includes(Buffer.from(bits)), name);
    }

    const second = start("--port", "0", "--assets", assetsDir, "--store", store);
    try {
      const origin = await second.origin;
      const read = await fetch(`${origin}/v1/shares/${who.id}`);
      assert.equal(read.status, 200);
      assert.match((await unseal(who.id, await read.arrayBuffer(), "cad-share/2 manifest")).toString(), /"manifest\.json"/);
      assert.equal((await fetch(`${origin}/v1/shares/${who.id}/packs/${packId}`)).status, 200);
      // Committed again, the listing of what the share holds comes from the files.
      const again = await share(origin, who, BUNDLE);
      assert.equal(again.committed.status, 200);
      assert.equal((await fetch(`${origin}/v1/shares/${who.id}`, { method: "DELETE", headers: { Authorization: `Bearer ${who.write}` } })).status, 204);
    } finally {
      await second.stop();
    }
    assert.deepEqual(readdirSync(store), []);
  });

  test("cuts off a zip that fails part way, never ending it as if whole, and serves on", async () => {
    const store = join(root, "cut");
    const who = newShare();
    const first = start("--port", "0", "--assets", assetsDir, "--store", store);
    let packId;
    try {
      const made = await share(await first.origin, who, BUNDLE, [["juno.py", "print('juno')\n"], ["lib/head.py", "HEAD = 1\n"]]);
      assert.equal(made.committed.status, 201);
      packId = made.packId;
    } finally {
      await first.stop();
    }
    // The pack's sealed bytes, spoilt where it is kept: it no longer opens.
    const kept = join(store, `${encodeURIComponent(`s/${await nameOf(who.id)}/p/${packId}`)}.bin`);
    writeFileSync(kept, randomBytes(readFileSync(kept).length));

    const second = start("--port", "0", "--assets", assetsDir, "--store", store);
    try {
      const origin = await second.origin;
      const zip = await fetch(`${origin}/${who.id}.zip`);
      assert.equal(zip.status, 200);
      await assert.rejects(zip.arrayBuffer());
      assert.equal((await fetch(`${origin}/v1/shares/${who.id}`)).status, 200, "it serves on");
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
    assert.deepEqual(made.customMetadata, { a: "1" });
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
    assert.equal(await bucket.put("k", new Uint8Array([4]), { onlyIf: { etagMatches: made.etag } }), null, "no object matches no etag");
    assert.throws(() => bucket.put("k", null, { customMetadata: { bytes: 1 } }), TypeError, "metadata is strings");
  });

  test("the bucket lists by prefix, in order, page by page with a cursor, its metadata only where asked for", async () => {
    const bucket = new LocalBucket(null, { pageSize: 2 });
    for (const key of ["s/b/2", "s/a/2", "s/a/10", "s/a/1", "t/a/1"]) await bucket.put(key, key, { customMetadata: { key } });
    const first = await bucket.list({ prefix: "s/a/" });
    assert.deepEqual(first.objects.map((object) => object.key), ["s/a/1", "s/a/10"]);
    assert.equal(first.truncated, true);
    assert.equal(first.objects[0].customMetadata, undefined);
    assert.equal(first.objects[0].size, 5);
    const rest = await bucket.list({ prefix: "s/a/", cursor: first.cursor });
    assert.deepEqual(rest.objects.map((object) => object.key), ["s/a/2"]);
    assert.equal(rest.truncated, false);
    assert.equal(rest.cursor, undefined);
    const included = await bucket.list({ prefix: "s/b/", include: ["customMetadata"] });
    assert.deepEqual(included.objects.map((object) => object.customMetadata), [{ key: "s/b/2" }]);
    const one = await bucket.list({ prefix: "s/", limit: 1 });
    assert.equal(one.objects.length, 1);
    assert.equal(one.truncated, true);
    assert.throws(() => bucket.list({ limit: 1001 }), RangeError);
    assert.throws(() => bucket.list({ delimiter: "/" }), TypeError, "what it does not emulate it refuses");
  });

  test("the bucket deletes up to 1000 keys a call, and a key that holds nothing is no error", async () => {
    const bucket = new LocalBucket();
    for (const key of ["a", "b", "c"]) await bucket.put(key, key);
    await bucket.delete(["a", "c", "absent"]);
    assert.deepEqual(await bucket.keys(), ["b"]);
    await assert.rejects(bucket.delete(Array.from({ length: 1001 }, (_, index) => `k${index}`)), RangeError);
    await bucket.delete(Array.from({ length: 1000 }, (_, index) => `k${index}`));
  });

  test("_headers adds its headers to the static answers it names, in order and joined, and is never served", async () => {
    const dir = mkdtempSync(join(root, "headers-"));
    mkdirSync(join(dir, "assets"));
    writeFileSync(join(dir, "assets", "app.js"), "export {};\n");
    writeFileSync(join(dir, "notes.txt"), "notes\n");
    writeFileSync(join(dir, "_headers"), "# every file\n/*\n  X-Robots-Tag: noindex\n/assets/*\n  X-Robots-Tag: nofollow\n  Cache-Control: public, max-age=60\n");
    const module = { fetch: async () => new Response("the Worker", { status: 418 }) };
    const answer = platform({ env: { ASSETS: localAssets(dir) }, config: { assets: {} }, module });
    const script = await answer(new Request("http://share.test/assets/app.js"), "127.0.0.1");
    assert.equal(script.headers.get("X-Robots-Tag"), "noindex, nofollow");
    assert.equal(script.headers.get("Cache-Control"), "public, max-age=60");
    assert.equal(await script.text(), "export {};\n");
    const notes = await answer(new Request("http://share.test/notes.txt"), "127.0.0.1");
    assert.equal(notes.headers.get("X-Robots-Tag"), "noindex");
    assert.equal((await answer(new Request("http://share.test/_headers"), "127.0.0.1")).status, 418, "no file: the Worker's");

    writeFileSync(join(dir, "_headers"), "/assets/:name\n  X-Robots-Tag: noindex\n");
    await assert.rejects(localAssets(dir).headersFor("/assets/app.js"), /_headers, line 1/);
  });

  test("the routing and the bindings follow wrangler.jsonc: the Worker first for the API and HTML, two limiters, the defaults", async () => {
    const config = await readConfig(join(APP_ROOT, "wrangler.jsonc"));
    assert.equal(config.main, "src/worker.mjs");
    assert.deepEqual(config.r2_buckets.map((bucket) => bucket.binding), ["SHARES"]);
    assert.deepEqual(config.ratelimits, [
      { name: "LIMITER", namespace_id: "47201", simple: { limit: 10, period: 60 } },
      { name: "LIMITER_PACKS", namespace_id: "47202", simple: { limit: 60, period: 60 } },
    ]);
    assert.deepEqual(Object.fromEntries(Object.entries(config.vars).map(([name, value]) => [name, Number(value)])), { ...DEFAULTS });
    assert.equal(config.assets.binding, "ASSETS");
    assert.equal(config.assets.directory, "./viewer");
    const first = config.assets.run_worker_first;
    for (const path of ["/v1/shares/abc", "/v1/shares/abc/packs/def", "/index.html", "/deep/page.html"]) assert.ok(runsWorkerFirst(first, path), path);
    for (const path of ["/", "/assets/app.js", "/AAAAAAAAAAAAAAAAAAAAAA"]) assert.ok(!runsWorkerFirst(first, path), path);
    assert.ok(!runsWorkerFirst(["/v1/*", "!/v1/open/*"], "/v1/open/x"));
    assert.ok(runsWorkerFirst(true, "/anything"));
  });
});
