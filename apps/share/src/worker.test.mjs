// The Worker's contract (README.md), run on the real module over the local stand-ins for its bindings,
// with a clock of the test's own that the bucket uploads by too. A share is opened here as the page opens
// one, with this file's own HKDF and AES-GCM, and its files' zip is read back by Python's zipfile, so what
// the service stores and serves is held to the protocol and the zip format rather than to the Worker's own
// reading of them.

import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash, randomBytes, webcrypto } from "node:crypto";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, test } from "node:test";
import { crc32, gunzipSync, gzipSync } from "node:zlib";

import { LocalBucket, allowAll, localAssets } from "./local.mjs";
import { BACKSTOP_DAYS, DEFAULTS, FORMAT, HOME, MAX_FILES, ZIP64, derive, handle, seal, zipOf } from "./worker.mjs";

// The service writes nothing to the console: every call made while this file runs is caught, and fails it.
const logged = [];
for (const method of ["debug", "dir", "error", "info", "log", "table", "trace", "warn"]) {
  console[method] = () => { logged.push(method); };
}
after(() => assert.deepEqual(logged, [], "the service wrote to the console"));

const DAY = 24 * 60 * 60 * 1000;
const START = Date.parse("2026-03-01T12:00:00.000Z");
const ORIGIN = "https://share.test";
const ADDRESS = "203.0.113.7";
const SEALING = 12 + 16; // the IV before, the tag after

const INLINE = "globalThis.__boot = 1;";
const INDEX = `<!doctype html><html><head><script>${INLINE}</script>` +
  `<script type="module" src="./assets/app.js"></script></head><body></body></html>`;
const assetsDir = mkdtempSync(join(tmpdir(), "share-assets-"));
writeFileSync(join(assetsDir, "index.html"), INDEX);
mkdirSync(join(assetsDir, "assets"));
writeFileSync(join(assetsDir, "assets", "app.js"), "export {};\n");
after(() => rmSync(assetsDir, { recursive: true, force: true }));

const b64url = (bytes) => Buffer.from(bytes).toString("base64url");
const sha256 = (data) => createHash("sha256").update(data).digest("hex");
const hex = (bytes) => Buffer.from(bytes).toString("hex");
const utf8 = (text) => new TextEncoder().encode(text);

function newShare() {
  return { id: b64url(randomBytes(16)), write: b64url(randomBytes(32)), delete: b64url(randomBytes(32)) };
}

/** The service over a bucket and a clock of the test's own. Every answer is held to what every answer
 * carries: X-Robots-Tag, and no CORS header. */
function service({ limiter = allowAll, packLimiter = allowAll, pageSize, Bucket = LocalBucket, ...vars } = {}) {
  const time = { at: START };
  const now = () => time.at;
  const bucket = new Bucket(null, { now, pageSize });
  const env = { SHARES: bucket, ASSETS: localAssets(assetsDir), LIMITER: limiter, LIMITER_PACKS: packLimiter, ...vars };
  async function call(method, path, { headers = {}, body } = {}) {
    const request = new Request(`${ORIGIN}${path}`, {
      method,
      body,
      headers: { "CF-Connecting-IP": ADDRESS, ...headers },
      duplex: body instanceof ReadableStream ? "half" : undefined,
    });
    const response = await handle(request, env, { now });
    assert.equal(response.headers.get("X-Robots-Tag"), "noindex, nofollow", `${method} ${path}`);
    for (const name of response.headers.keys()) assert.ok(!name.startsWith("access-control-"), `${method} ${path}: ${name}`);
    return response;
  }
  return { env, bucket, time, now, call };
}

/** A bucket that runs a step of the test's just before the first put to a key ending as given: another
 * client's request, landing between what this one read and what it writes. */
class Racing extends LocalBucket {
  #before = [];

  beforePut(suffix, run) {
    this.#before.push({ suffix, run });
  }

  async put(key, value, options) {
    const index = this.#before.findIndex(({ suffix }) => key.endsWith(suffix));
    if (index >= 0) await this.#before.splice(index, 1)[0].run();
    return super.put(key, value, options);
  }
}

// ---- shares as the command makes them, and as the page opens them ---------------------------------

/** Packs, one a group of [path, content]: each file's gzip member back to back, and the manifest's entry
 * for each file, saying where its member lies. */
function packed(...groups) {
  const packs = [];
  const files = {};
  for (const group of groups) {
    const members = group.map(([, content]) => gzipSync(Buffer.from(content)));
    const bytes = new Uint8Array(Buffer.concat(members));
    const id = sha256(bytes);
    let offset = 0;
    group.forEach(([path, content], index) => {
      files[path] = { sha256: sha256(content), bytes: Buffer.byteLength(content), at: [[id, offset, members[index].length]] };
      offset += members[index].length;
    });
    packs.push({ id, bytes });
  }
  return { packs, files };
}

/** A share manifest: the bundle's files as its view, and the files that made it (none unless given), with the
 * document's name, its entry and what made it. */
const manifestOf = (view, { files = {}, name = "juno", entry = null, made = null } = {}) =>
  ({ format: FORMAT, name, entry, made, view, files });
const BUNDLE = [["manifest.json", '{"format":"view-bundle/1"}'], ["structure.json", '{"tree":["a part"]}']];
const MADE = { cad: "0.11.17", build123d: "0.13.0", OCP: "8.0.1.1.0", python: "3.13.18", system: "Linux", arch: "x86_64" };

/** A write's headers: its two secrets', and the body's length where it has one (a stream has none). */
function writeHeaders(share, body) {
  const length = body instanceof ReadableStream ? {} : { "Content-Length": String(body.byteLength) };
  return { Authorization: `Bearer ${share.write}`, "Cad-Delete-Hash": sha256(share.delete), ...length };
}

function putPack(svc, share, pack, { headers = {}, body = pack.bytes } = {}) {
  return svc.call("PUT", `/v1/shares/${share.id}/packs/${pack.id}`, { body, headers: { ...writeHeaders(share, body), ...headers } });
}

function commit(svc, share, manifest, { headers = {} } = {}) {
  const body = manifest instanceof Uint8Array || manifest instanceof ReadableStream ? manifest
    : utf8(typeof manifest === "string" ? manifest : JSON.stringify(manifest));
  return svc.call("PUT", `/v1/shares/${share.id}`, {
    body,
    headers: { ...writeHeaders(share, body), "Content-Type": "application/json", ...headers },
  });
}

/** A share as the command makes one: each pack uploaded, then the manifest of their files committed. */
async function shared(svc, share, ...groups) {
  const { packs, files } = packed(...groups);
  for (const pack of packs) assert.equal((await putPack(svc, share, pack)).status, 201);
  return { packs, files, committed: await commit(svc, share, manifestOf(files)) };
}

function remove(svc, share, secret = share.delete) {
  return svc.call("DELETE", `/v1/shares/${share.id}`, { headers: { Authorization: `Bearer ${secret}` } });
}

/** What the protocol derives from an id, by this file's own HKDF: the key, and where the share is stored. */
async function derived(id) {
  const material = await webcrypto.subtle.importKey("raw", utf8(id), "HKDF", false, ["deriveBits"]);
  const bits = (info) => webcrypto.subtle.deriveBits({ name: "HKDF", hash: "SHA-256", salt: utf8("cad-share/2"), info: utf8(info) }, material, 256);
  const keyBytes = new Uint8Array(await bits("key"));
  return {
    keyBytes,
    key: await webcrypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["decrypt"]),
    prefix: `s/${hex(new Uint8Array(await bits("name")))}/`,
  };
}

async function unseal(key, stored, aad) {
  const bytes = new Uint8Array(stored);
  return new Uint8Array(await webcrypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12), additionalData: utf8(aad) }, key, bytes.slice(12)));
}

/** A share's view (or its files) as the page reads it: its manifest and each pack it names fetched from the
 * API, opened under the key its id derives with the AAD that names each, ranges joined and gunzipped, every
 * file held to its entry's size and SHA-256. */
async function openShare(svc, id, map = "view") {
  const { key } = await derived(id);
  const answer = await svc.call("GET", `/v1/shares/${id}`);
  assert.equal(answer.status, 200);
  const manifest = JSON.parse(new TextDecoder().decode(await unseal(key, await answer.arrayBuffer(), "cad-share/2 manifest")));
  const packs = new Map();
  const files = {};
  for (const [path, entry] of Object.entries(manifest[map])) {
    const member = [];
    for (const [pack, offset, length] of entry.at) {
      if (!packs.has(pack)) {
        const got = await svc.call("GET", `/v1/shares/${id}/packs/${pack}`);
        assert.equal(got.status, 200, `pack ${pack}`);
        packs.set(pack, await unseal(key, await got.arrayBuffer(), `cad-share/2 pack ${pack}`));
      }
      member.push(packs.get(pack).subarray(offset, offset + length));
    }
    const content = gunzipSync(Buffer.concat(member));
    assert.equal(content.length, entry.bytes, path);
    assert.equal(sha256(content), entry.sha256, path);
    files[path] = content.toString();
  }
  return files;
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

/** The share's keys in the bucket, each without the prefix its id derives. */
async function held(svc, id) {
  const { prefix } = await derived(id);
  const keys = await svc.bucket.keys();
  assert.ok(keys.every((key) => key.startsWith("s/")));
  return keys.filter((key) => key.startsWith(prefix)).map((key) => key.slice(prefix.length));
}

/** The bucket's lifecycle rule, run at the clock's time: every object uploaded BACKSTOP_DAYS ago or more
 * is deleted (R2 deletes such an object within a day after, never before). */
async function lifecycle(svc) {
  const old = [];
  for (let cursor; ;) {
    const page = await svc.bucket.list(cursor === undefined ? {} : { cursor });
    for (const object of page.objects) if (object.uploaded.getTime() + BACKSTOP_DAYS * DAY <= svc.now()) old.push(object.key);
    if (!page.truncated) break;
    cursor = page.cursor;
  }
  if (old.length) await svc.bucket.delete(old);
}

// ---- the files' zip, and an independent reader of it ----------------------------------------------

const gz = (content) => gzipSync(Buffer.from(content));

/** One pack of the members given, back to back: its id and bytes, and the range each member lies in. */
function packOf(...members) {
  const bytes = new Uint8Array(Buffer.concat(members));
  const id = sha256(bytes);
  let offset = 0;
  const at = members.map((member) => {
    const range = [id, offset, member.length];
    offset += member.length;
    return range;
  });
  return { id, bytes, at };
}

/** A manifest's entry for `content`, its member at the ranges given. */
const entryOf = (content, ...at) => ({ sha256: sha256(content), bytes: Buffer.byteLength(content), at });

/** A gzip member of `content` not of the plain form the command writes: its header holds the flags given and
 * what they say (FEXTRA, FNAME), as other gzip writers make one. */
function unplain(content, { name = "n.txt", extra = null } = {}) {
  const member = gz(content);
  const fields = [];
  if (extra) fields.push(Buffer.from([extra.length & 0xff, extra.length >> 8]), Buffer.from(extra));
  if (name) fields.push(Buffer.from(`${name}\0`, "latin1"));
  const header = Buffer.from(member.subarray(0, 10));
  header[3] = (extra ? 4 : 0) | (name ? 8 : 0);
  return Buffer.concat([header, ...fields, member.subarray(10)]);
}

/** A bucket that records the key of every get: what a read fetched. */
class Counting extends LocalBucket {
  gets = [];

  async get(key, options) {
    this.gets.push(key);
    return super.get(key, options);
  }
}

const zipsDir = mkdtempSync(join(tmpdir(), "share-zips-"));
after(() => rmSync(zipsDir, { recursive: true, force: true }));

// Python's zipfile, a reader the service shares no code with: each entry as its central directory and local
// header say, the SHA-256 of its stored data as it lies in the zip, and (`whole`) its bytes, every CRC-32
// checked first. `names` answers the names alone; `headers` reads no entry's data out.
const READER = String.raw`
import base64, hashlib, json, struct, sys, zipfile
path, mode = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(path) as archive:
    infos = archive.infolist()
    if mode == "names":
        print(json.dumps([info.filename for info in infos]))
        sys.exit()
    if mode == "whole":
        bad = archive.testzip()
        assert bad is None, bad
    entries = []
    for info in infos:
        archive.fp.seek(info.header_offset)
        local = struct.unpack("<IHHHHHIIIHH", archive.fp.read(30))
        name = archive.fp.read(local[9])
        extra = archive.fp.read(local[10])
        raw = archive.fp.read(info.compress_size)
        entries.append({
            "name": info.filename, "folder": info.is_dir(), "flags": info.flag_bits, "time": list(info.date_time),
            "method": info.compress_type, "crc": info.CRC, "compressed": info.compress_size, "size": info.file_size,
            "offset": info.header_offset, "system": info.create_system, "version": info.create_version,
            "needs": info.extract_version, "mode": info.external_attr >> 16, "dos": info.external_attr & 0xFF,
            "local": {"signature": local[0], "needs": local[1], "flags": local[2], "method": local[3], "time": local[4],
                      "date": local[5], "crc": local[6], "compressed": local[7], "size": local[8],
                      "name": name.decode("utf-8"), "extra": extra.hex()},
            "raw": hashlib.sha256(raw).hexdigest(),
            "data": base64.b64encode(archive.read(info)).decode() if mode == "whole" else None,
        })
print(json.dumps(entries))
`;

function readZip(bytes, mode = "whole") {
  const file = join(zipsDir, `${randomBytes(8).toString("hex")}.zip`);
  writeFileSync(file, bytes);
  try {
    return JSON.parse(execFileSync("python3", ["-I", "-c", READER, file, mode], { encoding: "utf8", maxBuffer: 1 << 28 }));
  } finally {
    rmSync(file, { force: true });
  }
}

/** A share's zip, fetched and read back. */
async function zipOfShare(svc, id, mode = "whole") {
  const answer = await svc.call("GET", `/${id}.zip`);
  assert.equal(answer.status, 200);
  const bytes = new Uint8Array(await answer.arrayBuffer());
  return { answer, bytes, entries: readZip(bytes, mode) };
}

/** Each file entry held to what the zip format and the amendment ask: UTF-8 names, 1980-01-01 00:00, rw-r--r--
 * made on UNIX, the same in the local header as in the central directory. */
function assertFileEntry(entry, { content, method = 8 }) {
  assert.equal(entry.folder, false, entry.name);
  assert.equal(entry.method, method, entry.name);
  assert.equal(entry.flags, 0x800, entry.name);
  assert.deepEqual(entry.time, [1980, 1, 1, 0, 0, 0], entry.name);
  assert.equal(entry.system, 3, entry.name);
  assert.equal(entry.mode, 0o100644, entry.name);
  assert.equal(entry.local.signature, 0x04034b50, entry.name);
  assert.equal(entry.local.name, entry.name);
  for (const field of ["flags", "method", "crc"]) assert.equal(entry.local[field], entry[field], `${entry.name}: ${field}`);
  assert.equal(entry.local.date, 0x21, entry.name);
  assert.equal(entry.local.time, 0, entry.name);
  if (content !== undefined) {
    assert.equal(entry.size, Buffer.byteLength(content), entry.name);
    assert.equal(entry.crc, crc32(Buffer.from(content)), entry.name);
    if (entry.data !== null) assert.deepEqual(Buffer.from(entry.data, "base64"), Buffer.from(content), entry.name);
  }
}

/** The zip's last records: the end of central directory record, and the Zip64 ones before it where present. */
function endOf(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const at = bytes.byteLength - 22;
  assert.equal(view.getUint32(at, true), 0x06054b50, "the zip ends with its end of central directory record");
  const end = { count: view.getUint16(at + 10, true), size: view.getUint32(at + 12, true), offset: view.getUint32(at + 16, true) };
  if (view.getUint32(at - 20, true) !== 0x07064b50) return { end, zip64: null };
  const record = Number(view.getBigUint64(at - 20 + 8, true));
  assert.equal(record, at - 20 - 56, "the locator names the Zip64 record right before it");
  assert.equal(view.getUint32(record, true), 0x06064b50);
  const read = (offset) => Number(view.getBigUint64(record + offset, true));
  return { end, zip64: { count: read(32), size: read(40), offset: read(48) } };
}

// ---- the tests ------------------------------------------------------------------------------------

describe("the names and the sealing", () => {
  test("are the protocol's test vectors: the key and the name, and both sealed objects with a zero IV", async () => {
    const id = "0sHbv5_DYsmyh0xEOGyhAw";
    const keyBytes = await derive(id, "key");
    assert.equal(hex(keyBytes), "bf9fb149a034b6d5702170bbbab7409bdf0454963ddd6cdce46bf73006310fe6");
    assert.equal(hex(await derive(id, "name")), "38d4a8b66f195cc29d2775a039a5623334ff97adfa483315e6a881affa311744");
    assert.equal((await derived(id)).prefix, "s/38d4a8b66f195cc29d2775a039a5623334ff97adfa483315e6a881affa311744/");

    const key = await webcrypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["encrypt"]);
    const zero = new Uint8Array(12);
    const manifest = await seal(key, utf8('{"format":"cad-share/2","files":{}}'), "cad-share/2 manifest", zero);
    assert.equal(hex(manifest), "000000000000000000000000" +
      "1805bb723d8d97c83c5276bc082386bfa6fb1c0f261cab97e775011c9ba9236e4a7453650be41051cebe7d4be9d018a48bf8cf");
    const pack = utf8("pack bytes");
    assert.equal(sha256(pack), "d61037e21c7e5fc5318069739439f61ccea49f6b11a1dad1ecf15cb0d831e680");
    assert.equal(hex(await seal(key, pack, `cad-share/2 pack ${sha256(pack)}`, zero)),
      "000000000000000000000000" + "1346be766f828fc87b1b4228fcd3958832a517117534968df561");
  });
});

describe("a pack's upload", () => {
  test("stores it sealed under the share's name with the AAD that names it, and makes the share's owner (201)", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [pack] } = packed(BUNDLE);
    const made = await putPack(svc, share, pack);
    assert.equal(made.status, 201);
    assert.deepEqual(await made.json(), { pack: pack.id, bytes: pack.bytes.byteLength + SEALING });
    assert.deepEqual(await held(svc, share.id), ["owner", `p/${pack.id}`]);

    const { key, prefix } = await derived(share.id);
    const owner = await svc.bucket.head(`${prefix}owner`);
    assert.equal(owner.size, 0);
    assert.deepEqual(owner.customMetadata, { format: FORMAT, write: sha256(share.write), delete: sha256(share.delete) });
    const stored = await (await svc.bucket.get(`${prefix}p/${pack.id}`)).arrayBuffer();
    assert.deepEqual(await unseal(key, stored, `cad-share/2 pack ${pack.id}`), pack.bytes);
    await assert.rejects(unseal(key, stored, "cad-share/2 manifest"));
    await assert.rejects(unseal(key, stored, `cad-share/2 pack ${sha256("another")}`));

    // Again: the same pack, sealed under a fresh IV; harmless.
    assert.equal((await putPack(svc, share, pack)).status, 201);
    const again = await (await svc.bucket.get(`${prefix}p/${pack.id}`)).arrayBuffer();
    assert.notDeepEqual(new Uint8Array(again).slice(0, 12), new Uint8Array(stored).slice(0, 12));
    assert.deepEqual(await unseal(key, again, `cad-share/2 pack ${pack.id}`), pack.bytes);
    assert.deepEqual(await held(svc, share.id), ["owner", `p/${pack.id}`]);
  });

  test("refuses what the protocol refuses, each with its status, and stores nothing", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [pack] } = packed(BUNDLE);
    await refusal(await putPack(svc, { ...share, id: "short" }, pack), 400, "bad_id");
    await refusal(await putPack(svc, { ...share, id: `${share.id.slice(1)}=` }, pack), 400, "bad_id");
    for (const id of [pack.id.toUpperCase(), pack.id.slice(1), ""]) {
      const response = await svc.call("PUT", `/v1/shares/${share.id}/packs/${id}`, { body: pack.bytes, headers: writeHeaders(share, pack.bytes) });
      await refusal(response, 400, "bad_pack_id");
    }
    for (const authorization of ["", `Basic ${share.write}`, `Bearer`]) {
      const response = await putPack(svc, share, pack, { headers: { Authorization: authorization } });
      await refusal(response, 401, "unauthorized");
      assert.equal(response.headers.get("WWW-Authenticate"), "Bearer");
    }
    await refusal(await putPack(svc, share, pack, { headers: { Authorization: "Bearer short" } }), 400, "bad_secret");
    await refusal(await putPack(svc, share, pack, { headers: { Authorization: `Bearer ${share.write}=` } }), 400, "bad_secret");
    await refusal(await putPack(svc, share, pack, { headers: { "Cad-Delete-Hash": "" } }), 400, "bad_delete_hash");
    await refusal(await putPack(svc, share, pack, { headers: { "Cad-Delete-Hash": sha256(share.delete).toUpperCase() } }), 400, "bad_delete_hash");
    await refusal(await putPack(svc, share, pack, { headers: { "Cad-Delete-Hash": share.delete } }), 400, "bad_delete_hash");
    await refusal(await putPack(svc, share, pack, { body: utf8("other bytes") }), 400, "bad_pack");
    assert.deepEqual(await svc.bucket.keys(), []);
  });

  test("without a Content-Length is refused (411), and over MAX_PACK_BYTES (413) by its length or by its body", async () => {
    const svc = service({ MAX_PACK_BYTES: "64" });
    const share = newShare();
    const stream = (bytes) => new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } });
    const fits = { id: sha256(new Uint8Array(64)), bytes: new Uint8Array(64) };
    const over = { id: sha256(new Uint8Array(65)), bytes: new Uint8Array(65) };
    await refusal(await putPack(svc, share, fits, { body: stream(fits.bytes) }), 411, "length_required");
    await refusal(await putPack(svc, share, over), 413, "too_large");
    await refusal(await putPack(svc, share, over, { body: stream(over.bytes), headers: { "Content-Length": "40" } }), 413, "too_large");
    assert.deepEqual(await svc.bucket.keys(), []);
    assert.equal((await putPack(svc, share, fits)).status, 201);
    assert.equal(DEFAULTS.MAX_PACK_BYTES, 8 * 1024 * 1024);
  });

  test("to a share another write secret made is refused (403), and changes nothing", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [first, second] } = packed(BUNDLE, [["other.json", "{}"]]);
    assert.equal((await putPack(svc, share, first)).status, 201);
    const before = await held(svc, share.id);
    const other = { ...newShare(), id: share.id };
    await refusal(await putPack(svc, other, second), 403, "forbidden");
    await refusal(await putPack(svc, other, first), 403, "forbidden");
    assert.deepEqual(await held(svc, share.id), before);
    const { prefix } = await derived(share.id);
    assert.equal((await svc.bucket.head(`${prefix}owner`)).customMetadata.write, sha256(share.write));
  });

  test("that loses the owner's put to another write reads the owner made, and goes on only if it holds its secret", async () => {
    const svc = service({ Bucket: Racing });
    const { packs: [first, second] } = packed(BUNDLE, [["other.json", "{}"]]);
    const share = newShare();
    const other = { ...newShare(), id: share.id };
    svc.bucket.beforePut("/owner", async () => assert.equal((await putPack(svc, other, second)).status, 201));
    await refusal(await putPack(svc, share, first), 403, "forbidden");
    assert.deepEqual(await held(svc, share.id), ["owner", `p/${second.id}`]);

    const mine = newShare();
    svc.bucket.beforePut("/owner", async () => assert.equal((await putPack(svc, mine, second)).status, 201));
    assert.equal((await putPack(svc, mine, first)).status, 201);
    assert.deepEqual(await held(svc, mine.id), ["owner", `p/${first.id}`, `p/${second.id}`].sort());
  });
});

describe("a commit", () => {
  test("makes the share (201): the manifest sealed as it was sent, and the share opens as the page opens it", async () => {
    const svc = service();
    const share = newShare();
    const { packs, files, committed } = await shared(svc, share, BUNDLE);
    assert.equal(committed.status, 201);
    const expires = new Date(START + 7 * DAY).toISOString();
    const bytes = packs[0].bytes.byteLength + SEALING;
    assert.deepEqual(await committed.json(), { id: share.id, expires, bytes, files: 2 });

    const { key, prefix } = await derived(share.id);
    assert.deepEqual(await held(svc, share.id), ["manifest", "owner", `p/${packs[0].id}`]);
    const object = await svc.bucket.head(`${prefix}manifest`);
    assert.deepEqual(object.customMetadata, { format: FORMAT, expires, bytes: String(bytes), files: "2" });

    const read = await svc.call("GET", `/v1/shares/${share.id}`);
    assert.equal(read.status, 200);
    assert.equal(read.headers.get("Content-Type"), "application/octet-stream");
    assert.equal(read.headers.get("Cache-Control"), "no-store");
    assert.equal(read.headers.get("Cad-Share-Expires"), expires);
    const stored = await read.arrayBuffer();
    assert.equal(read.headers.get("Content-Length"), String(stored.byteLength));
    assert.deepEqual(await unseal(key, stored, "cad-share/2 manifest"), utf8(JSON.stringify(manifestOf(files))));
    assert.deepEqual(await openShare(svc, share.id), Object.fromEntries(BUNDLE));

    const head = await svc.call("HEAD", `/v1/shares/${share.id}`);
    assert.equal(head.status, 200);
    assert.equal(head.body, null);
    for (const name of ["Content-Type", "Content-Length", "Cache-Control", "Cad-Share-Expires"]) {
      assert.equal(head.headers.get(name), read.headers.get(name), name);
    }
  });

  test("names a file split over two packs by its ranges, joined in order", async () => {
    const svc = service();
    const share = newShare();
    const large = JSON.stringify(Array.from({ length: 400 }, (_, index) => ({ index, mesh: randomBytes(24).toString("hex") })));
    const member = gzipSync(Buffer.from(large));
    const cut = Math.floor(member.length / 2);
    const tail = gzipSync(Buffer.from(BUNDLE[0][1]));
    const first = { bytes: new Uint8Array(member.subarray(0, cut)) };
    const second = { bytes: new Uint8Array(Buffer.concat([member.subarray(cut), tail])) };
    for (const pack of [first, second]) {
      pack.id = sha256(pack.bytes);
      assert.equal((await putPack(svc, share, pack)).status, 201);
    }
    const manifest = manifestOf({
      "manifest.json": { sha256: sha256(BUNDLE[0][1]), bytes: BUNDLE[0][1].length, at: [[second.id, member.length - cut, tail.length]] },
      "parts/a/mesh.json": { sha256: sha256(large), bytes: large.length, at: [[first.id, 0, cut], [second.id, 0, member.length - cut]] },
    });
    assert.equal((await commit(svc, share, manifest)).status, 201);
    assert.deepEqual(await openShare(svc, share.id), { "manifest.json": BUNDLE[0][1], "parts/a/mesh.json": large });
  });

  test("again replaces the manifest (200), starts the 7 days again, and deletes only the packs neither manifest names", async () => {
    const svc = service();
    const share = newShare();
    const [manifestJson, a, b] = [["manifest.json", "{}"], ["a.json", '"a"'], ["b.json", '"b"']];
    const one = packed([manifestJson, a], [b]);
    const [p1, p2] = one.packs;
    const { packs: [p0] } = packed([["unused.json", "never named"]]);
    assert.equal((await putPack(svc, share, p0)).status, 201);
    for (const pack of [p1, p2]) assert.equal((await putPack(svc, share, pack)).status, 201);
    assert.equal((await commit(svc, share, manifestOf(one.files))).status, 201);
    // Named by neither this manifest nor one it replaced (it replaced none): gone.
    assert.deepEqual(await held(svc, share.id), ["manifest", "owner", `p/${p1.id}`, `p/${p2.id}`].sort());

    svc.time.at += 3 * DAY;
    const changed = [["manifest.json", '{"again":1}'], ["a.json", '"a, edited"']];
    const two = packed(changed);
    const [p3] = two.packs;
    assert.equal((await putPack(svc, share, p3)).status, 201);
    const again = await commit(svc, share, manifestOf({ ...two.files, "b.json": one.files["b.json"] }));
    assert.equal(again.status, 200);
    assert.equal((await again.json()).expires, new Date(svc.now() + 7 * DAY).toISOString());
    // p1 is the replaced manifest's alone: kept one commit more, for a page still fetching it.
    assert.deepEqual(await held(svc, share.id), ["manifest", "owner", `p/${p1.id}`, `p/${p2.id}`, `p/${p3.id}`].sort());

    svc.time.at += 1 * DAY;
    const three = packed([["b.json", '"b, edited"']]);
    const [p4] = three.packs;
    assert.equal((await putPack(svc, share, p4)).status, 201);
    assert.equal((await commit(svc, share, manifestOf({ ...two.files, ...three.files }))).status, 200);
    assert.deepEqual(await held(svc, share.id), ["manifest", "owner", `p/${p2.id}`, `p/${p3.id}`, `p/${p4.id}`].sort());
    assert.deepEqual(await openShare(svc, share.id), { "manifest.json": '{"again":1}', "a.json": '"a, edited"', "b.json": '"b, edited"' });

    // Past the first commit's 7 days, within the last one's.
    svc.time.at = START + 8 * DAY;
    assert.equal((await svc.call("HEAD", `/v1/shares/${share.id}`)).status, 200);
  });

  test("naming packs the share does not hold is refused (409), with each missing pack once, sorted", async () => {
    const svc = service();
    const share = newShare();
    const { packs, files } = packed([BUNDLE[0]], [BUNDLE[1]], [["c.json", "{}"]]);
    assert.equal((await putPack(svc, share, packs[0])).status, 201);
    const twice = { ...files, "d.json": { ...files["c.json"] } };
    const body = await refusal(await commit(svc, share, manifestOf(twice)), 409, "missing_packs");
    assert.deepEqual(body.missing, [packs[1].id, packs[2].id].sort());
    assert.deepEqual(await held(svc, share.id), ["owner", `p/${packs[0].id}`]);
  });

  test("is refused (413) where the packs it names hold more than MAX_SHARE_BYTES, and made where they hold as much", async () => {
    const { packs, files } = packed(BUNDLE, [["more.json", "more"]]);
    const size = packs.reduce((sum, pack) => sum + pack.bytes.byteLength + SEALING, 0);
    for (const [limit, status] of [[size, 201], [size - 1, 413]]) {
      const svc = service({ MAX_SHARE_BYTES: String(limit) });
      const share = newShare();
      for (const pack of packs) assert.equal((await putPack(svc, share, pack)).status, 201);
      const response = await commit(svc, share, manifestOf(files));
      if (status === 413) await refusal(response, 413, "share_too_large");
      else assert.equal(response.status, 201);
    }
    assert.equal(DEFAULTS.MAX_SHARE_BYTES, 256 * 1024 * 1024);
  });

  test("over MAX_MANIFEST_BYTES is refused (413), by its length or by its body, and without a length (411)", async () => {
    const { packs, files } = packed(BUNDLE);
    const text = JSON.stringify(manifestOf(files));
    const svc = service({ MAX_MANIFEST_BYTES: String(text.length) });
    const share = newShare();
    for (const pack of packs) assert.equal((await putPack(svc, share, pack)).status, 201);
    const padded = utf8(`${text} `);
    const stream = (bytes) => new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } });
    await refusal(await commit(svc, share, padded), 413, "too_large");
    await refusal(await commit(svc, share, stream(padded), { headers: { "Content-Length": String(text.length - 1) } }), 413, "too_large");
    await refusal(await commit(svc, share, stream(utf8(text))), 411, "length_required");
    assert.deepEqual(await held(svc, share.id), ["owner", `p/${packs[0].id}`]);
    assert.equal((await commit(svc, share, text)).status, 201, "a manifest of exactly the most bytes is made");
    assert.equal(DEFAULTS.MAX_MANIFEST_BYTES, 16 * 1024 * 1024);
  });

  test("refuses a manifest not of the protocol's shape (400), saying what, and stores none", async () => {
    const svc = service();
    const share = newShare();
    const { packs, files } = packed(BUNDLE);
    for (const pack of packs) assert.equal((await putPack(svc, share, pack)).status, 201);
    const entry = files["structure.json"];
    const [[pack, offset, length]] = entry.at;
    // A model's: its view, and its script among the files that made it.
    const good = manifestOf(files, { files: { "juno.py": entry }, entry: "juno.py", made: MADE });
    assert.equal((await commit(svc, newShare(), good)).status, 409, "of the shape, it is only missing its packs");
    const withMember = (change) => ({ ...good, ...change });
    const without = (name) => Object.fromEntries(Object.entries(good).filter(([member]) => member !== name));
    const withFile = (path, value = entry, map = "view") => withMember({ [map]: { ...good[map], [path]: value } });
    const withEntry = (change, map = "view") => withFile(map === "view" ? "structure.json" : "juno.py", { ...entry, ...change }, map);
    const made = (count) => Object.fromEntries(Array.from({ length: count }, (_, index) => [`lib${index}`, "1.0"]));
    const cases = [
      [utf8("not json"), /JSON/],
      [new Uint8Array([0x7b, 0xff, 0x7d]), /UTF-8/],
      ["[]", /a JSON object/],
      // The bundle's files alone, as a manifest was before it carried the files that made it.
      [{ format: FORMAT, files }, /has no name/],
      ...["format", "name", "entry", "made", "view", "files"].map((name) => [without(name), new RegExp(`has no ${name}\\.`)]),
      [withMember({ other: "x" }), /no "other"/],
      [withMember({ format: "cad-share/1" }), /format is "cad-share\/2"/],
      [withMember({ name: "" }), /name is its document's/],
      [withMember({ name: "x".repeat(201) }), /name is its document's/],
      [withMember({ name: 7 }), /name is its document's/],
      [withMember({ name: null }), /name is its document's/],
      [withMember({ name: "a\ud800" }), /name is its document's/],
      [withMember({ name: "a\nb" }), /no control character/],
      [withMember({ name: "a\u007f" }), /no control character/],
      [withMember({ name: "a\u0085" }), /no control character/],
      [withMember({ entry: "absent.py" }), /entry is the path in its files/],
      [withMember({ entry: "structure.json" }), /entry is the path in its files/],
      [withMember({ entry: 1 }), /entry is the path in its files/],
      [withMember({ entry: "" }), /entry is the path in its files/],
      [withMember({ made: [] }), /made is null, or what built the model/],
      [withMember({ made: "0.11.17" }), /made is null, or what built the model/],
      [withMember({ made: made(33) }), /at most 32 members/],
      [withMember({ made: { cad: 1 } }), /made\["cad"\] is not/],
      [withMember({ made: { cad: null } }), /made\["cad"\] is not/],
      [withMember({ made: { cad: "1".repeat(101) } }), /made\["cad"\] is not/],
      [withMember({ made: { cad: "a\udc00" } }), /made\["cad"\] is not/],
      [withMember({ made: { ["x".repeat(101)]: "1" } }), /made\["x+/],
      [withMember({ view: [] }), /view is an object/],
      [withMember({ view: null }), /view is an object/],
      [withMember({ files: [] }), /files is an object/],
      [withMember({ files: "juno.py" }), /files is an object/],
      [withMember({ view: { "structure.json": entry } }), /view lists the bundle's manifest\.json/],
      // The files' paths are held to the view's rules, each named as one of the files.
      [withFile("../juno.py", entry, "files"), /^files\["\.\.\/juno\.py"\]: a path has no empty, \. or \.\. segment\.$/],
      [withFile("/home/juno.py", entry, "files"), /^files\[.*relative/],
      [withFile("C:/juno.py", entry, "files"), /^files\[.*relative/],
      [withFile("lib\\head.py", entry, "files"), /^files\[.*relative/],
      [withFile("lib//head.py", entry, "files"), /^files\[.*empty/],
      [withFile("é".repeat(513), entry, "files"), /^files\[.*at most 1024 bytes/],
      [withFile("lib/head.py", null, "files"), /^files\["lib\/head\.py"\]: a file is an object/],
      [withEntry({ bytes: -1 }, "files"), /^files\["juno\.py"\]: bytes is a whole number/],
      [withEntry({ sha256: "x" }, "files"), /^files\["juno\.py"\]: sha256/],
      [withEntry({ at: [] }, "files"), /^files\["juno\.py"\]: at is one or more/],
      [withEntry({ at: [[pack, offset, length + 1000]] }, "files"), /past the end of pack/],
      [withFile(""), /empty/],
      [withFile("/etc/passwd"), /relative/],
      [withFile("a//b"), /empty/],
      [withFile("a/"), /empty/],
      [withFile("./a"), /\. or \.\./],
      [withFile("a/../b"), /\. or \.\./],
      [withFile("a\\b"), /relative/],
      [withFile("C:/a"), /relative/],
      [withFile("x".repeat(1025)), /at most 1024 bytes/],
      [withFile("é".repeat(513)), /at most 1024 bytes/],
      [withFile("a\ud800"), /text/],
      [withFile("thumbnail.png"), /thumbnail\.png/],
      [withFile("a.json", 0), /a file is an object/],
      [withFile("a.json", null), /a file is an object/],
      [withEntry({ name: "a" }), /no "name"/],
      [withEntry({ sha256: entry.sha256.toUpperCase() }), /sha256/],
      [withEntry({ sha256: undefined }), /sha256/],
      [withEntry({ bytes: -1 }), /bytes is a whole number/],
      [withEntry({ bytes: 1.5 }), /bytes is a whole number/],
      [withEntry({ bytes: "1" }), /bytes is a whole number/],
      [withEntry({ at: [] }), /at is one or more/],
      [withEntry({ at: "x" }), /at is one or more/],
      [withEntry({ at: [[pack, offset]] }), /each of at/],
      [withEntry({ at: [[pack.toUpperCase(), offset, length]] }), /each of at/],
      [withEntry({ at: [[pack, -1, length]] }), /each of at/],
      [withEntry({ at: [[pack, offset, 0.5]] }), /each of at/],
      [withEntry({ at: [[pack, offset, length + 1000]] }), /past the end of pack/],
    ];
    for (const [manifest, hint] of cases) {
      const body = await refusal(await commit(svc, share, manifest), 400, "bad_manifest");
      assert.match(body.hint, hint, JSON.stringify(manifest instanceof Uint8Array ? [...manifest] : manifest).slice(0, 120));
    }
    assert.deepEqual(await held(svc, share.id), ["owner", `p/${packs[0].id}`]);
  });

  test("takes every manifest of the shape: a model's, a file document's, and each member at its bounds", async () => {
    const svc = service();
    const share = newShare();
    const { packs, files } = packed(BUNDLE);
    for (const pack of packs) assert.equal((await putPack(svc, share, pack)).status, 201);
    const entry = files["structure.json"];
    const made = Object.fromEntries(Array.from({ length: 32 }, (_, index) => [`${"n".repeat(98)}${String(index).padStart(2, "0")}`, "v".repeat(100)]));
    const accepted = [
      // A file document: no entry, nothing that made it, its file among the files.
      manifestOf(files, { files: { "bracket.step": entry } }),
      // No files at all, an empty made, a name of one character.
      manifestOf(files, { name: "j", made: {} }),
      // 200 characters, each two UTF-16 units; 32 members of 100 characters each.
      manifestOf(files, { name: "🙂".repeat(200), files: { "juno.py": entry }, entry: "juno.py", made }),
      // A path of the view's again, and a thumbnail.png the build read: the files' own.
      manifestOf(files, { files: { "manifest.json": entry, "thumbnail.png": entry, "é/ü.py": entry }, entry: "é/ü.py", made: MADE }),
    ];
    for (const manifest of accepted) {
      const answer = await commit(svc, share, manifest);
      assert.ok(answer.status === 200 || answer.status === 201, JSON.stringify(manifest).slice(0, 120));
      const listed = Object.keys(manifest.view).length + Object.keys(manifest.files).length;
      assert.equal((await answer.json()).files, listed, "files counts the view's and the files' together");
    }
  });

  test("lists at most 200,000 files, its view's and its files' together", async () => {
    const svc = service();
    const share = newShare();
    const map = (from, count) => Array.from({ length: count }, (_, index) => `"f${from + index}":0`).join(",");
    const listing = (view, files) =>
      `{"format":"${FORMAT}","name":"juno","entry":null,"made":null,"view":{${map(0, view)}},"files":{${map(view, files)}}}`;
    const half = MAX_FILES / 2;
    assert.match((await refusal(await commit(svc, share, listing(half, half + 1)), 400, "bad_manifest")).hint, /at most 200000 files/);
    // As many is no refusal for their number (but for what the first of them is).
    assert.match((await refusal(await commit(svc, share, listing(half, half)), 400, "bad_manifest")).hint, /manifest\.json/);
  });

  test("refuses what a pack's upload refuses: a bad id, secret or hash (400), no Authorization (401), another's share (403)", async () => {
    const svc = service();
    const share = newShare();
    const { files } = await shared(svc, share, BUNDLE);
    const manifest = manifestOf(files);
    await refusal(await commit(svc, { ...share, id: "short" }, manifest), 400, "bad_id");
    await refusal(await commit(svc, share, manifest, { headers: { Authorization: "Bearer short" } }), 400, "bad_secret");
    await refusal(await commit(svc, share, manifest, { headers: { "Cad-Delete-Hash": "x" } }), 400, "bad_delete_hash");
    const unauthorized = await commit(svc, share, manifest, { headers: { Authorization: "" } });
    await refusal(unauthorized, 401, "unauthorized");
    assert.equal(unauthorized.headers.get("WWW-Authenticate"), "Bearer");
    await refusal(await commit(svc, { ...newShare(), id: share.id }, manifest), 403, "forbidden");
    assert.equal((await svc.call("GET", `/v1/shares/${share.id}`)).headers.get("Cad-Share-Expires"), new Date(START + 7 * DAY).toISOString());
  });

  test("whose manifest another commit replaced while it was checked is refused (409, no missing), and leaves the other's", async () => {
    const svc = service({ Bucket: Racing });
    const share = newShare();
    const { files } = await shared(svc, share, BUNDLE);
    const theirs = packed([["manifest.json", '{"theirs":1}']]);
    assert.equal((await putPack(svc, share, theirs.packs[0])).status, 201);
    svc.bucket.beforePut("/manifest", async () => {
      assert.equal((await commit(svc, share, manifestOf({ ...files, ...theirs.files }))).status, 200);
    });
    const lost = await refusal(await commit(svc, share, manifestOf(files)), 409, "conflict");
    assert.equal("missing" in lost, false);
    assert.equal((await openShare(svc, share.id))["manifest.json"], '{"theirs":1}');
  });

  test("two first commits at once: one makes the share (201); the other, put only if none is there, is refused (409)", async () => {
    const svc = service({ Bucket: Racing });
    const share = newShare();
    const { packs, files } = packed(BUNDLE);
    for (const pack of packs) assert.equal((await putPack(svc, share, pack)).status, 201);
    const other = { ...files, "manifest.json": files["manifest.json"], "structure.json": files["structure.json"] };
    svc.bucket.beforePut("/manifest", async () => assert.equal((await commit(svc, share, manifestOf(other))).status, 201));
    const lost = await refusal(await commit(svc, share, manifestOf(files)), 409, "conflict");
    assert.equal("missing" in lost, false);
    assert.deepEqual(await openShare(svc, share.id), Object.fromEntries(BUNDLE));
  });

  test("of a share whose manifest expired makes it anew (201), and keeps none of the packs it does not name", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [first, second], files } = await shared(svc, share, BUNDLE, [["b.json", '"b"']]);
    svc.time.at += 7 * DAY + 1;
    const { "b.json": _, ...rest } = files;
    const made = await commit(svc, share, manifestOf(rest));
    assert.equal(made.status, 201);
    assert.equal((await made.json()).expires, new Date(svc.now() + 7 * DAY).toISOString());
    assert.deepEqual(await held(svc, share.id), ["manifest", "owner", `p/${first.id}`]);
    assert.notEqual(first.id, second.id);
  });

  test("keeps EXPIRY_DAYS where the deployment sets it", async () => {
    const svc = service({ EXPIRY_DAYS: "2" });
    const { committed } = await shared(svc, newShare(), BUNDLE);
    assert.equal((await committed.json()).expires, new Date(START + 2 * DAY).toISOString());
    assert.equal(DEFAULTS.EXPIRY_DAYS, 7);
  });

  test("holds the files' packs to what the view's are: each stored (409), counted once in the share's size (413)", async () => {
    const view = packOf(gz(BUNDLE[0][1]), gz(BUNDLE[1][1]), gz("print('juno')\n"));
    const code = packOf(gz("HEAD = 1\n"));
    const files = {
      "juno.py": entryOf("print('juno')\n", view.at[2]), // in the view's pack: counted once
      "lib/head.py": entryOf("HEAD = 1\n", code.at[0]), // named by the files alone
    };
    const manifest = manifestOf({ "manifest.json": entryOf(BUNDLE[0][1], view.at[0]), "structure.json": entryOf(BUNDLE[1][1], view.at[1]) },
                                { files, entry: "juno.py", made: MADE });
    const size = view.bytes.byteLength + code.bytes.byteLength + 2 * SEALING;

    const svc = service({ MAX_SHARE_BYTES: String(size) });
    const share = newShare();
    assert.equal((await putPack(svc, share, view)).status, 201);
    const missing = await refusal(await commit(svc, share, manifest), 409, "missing_packs");
    assert.deepEqual(missing.missing, [code.id]);
    assert.equal((await putPack(svc, share, code)).status, 201);
    const made = await commit(svc, share, manifest);
    assert.equal(made.status, 201);
    assert.deepEqual(await made.json(), { id: share.id, expires: new Date(START + 7 * DAY).toISOString(), bytes: size, files: 4 });
    assert.deepEqual(await openShare(svc, share.id, "files"), { "juno.py": "print('juno')\n", "lib/head.py": "HEAD = 1\n" });

    const small = service({ MAX_SHARE_BYTES: String(size - 1) });
    for (const pack of [view, code]) assert.equal((await putPack(small, share, pack)).status, 201);
    await refusal(await commit(small, share, manifest), 413, "share_too_large");
  });

  test("keeps and deletes the files' packs as the view's: one only the replaced manifest's files name is kept one commit more", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [bundle], files: view } = packed(BUNDLE);
    const versions = ["print(1)\n", "print(2)\n", "print(3)\n"].map((code) => ({ code, pack: packOf(gz(code)) }));
    const stray = packOf(gz("named by no manifest"));
    const manifest = ({ code, pack }) => manifestOf(view, { files: { "juno.py": entryOf(code, pack.at[0]) }, entry: "juno.py", made: MADE });
    for (const pack of [bundle, stray, versions[0].pack]) assert.equal((await putPack(svc, share, pack)).status, 201);
    assert.equal((await commit(svc, share, manifest(versions[0]))).status, 201);
    assert.deepEqual(await held(svc, share.id), ["manifest", "owner", `p/${bundle.id}`, `p/${versions[0].pack.id}`].sort());

    assert.equal((await putPack(svc, share, versions[1].pack)).status, 201);
    assert.equal((await commit(svc, share, manifest(versions[1]))).status, 200);
    // The first script is the replaced manifest's: kept, for a download of it under way.
    assert.deepEqual(await held(svc, share.id),
                     ["manifest", "owner", `p/${bundle.id}`, `p/${versions[0].pack.id}`, `p/${versions[1].pack.id}`].sort());

    assert.equal((await putPack(svc, share, versions[2].pack)).status, 201);
    assert.equal((await commit(svc, share, manifest(versions[2]))).status, 200);
    assert.deepEqual(await held(svc, share.id),
                     ["manifest", "owner", `p/${bundle.id}`, `p/${versions[1].pack.id}`, `p/${versions[2].pack.id}`].sort());
    assert.deepEqual(await openShare(svc, share.id, "files"), { "juno.py": "print(3)\n" });
  });
});

describe("a manifest's read", () => {
  test("of an id with no manifest is 404, its packs uploaded or not, and of a bad id 400", async () => {
    const svc = service();
    const share = newShare();
    await refusal(await svc.call("GET", `/v1/shares/${share.id}`), 404, "not_found");
    await refusal(await svc.call("HEAD", `/v1/shares/${share.id}`), 404, "not_found");
    assert.equal((await putPack(svc, share, packed(BUNDLE).packs[0])).status, 201);
    await refusal(await svc.call("GET", `/v1/shares/${share.id}`), 404, "not_found");
    await refusal(await svc.call("GET", "/v1/shares/not-an-id"), 400, "bad_id");
    await refusal(await svc.call("GET", "/v1/shares/"), 400, "bad_id");
  });

  test("past the share's expiry deletes the whole share, its owner and packs too, and answers 404", async () => {
    const svc = service();
    const share = newShare();
    await shared(svc, share, BUNDLE, [["b.json", "{}"]]);
    svc.time.at += 7 * DAY - 1;
    assert.equal((await svc.call("HEAD", `/v1/shares/${share.id}`)).status, 200);
    svc.time.at += 1;
    await refusal(await svc.call("GET", `/v1/shares/${share.id}`), 404, "not_found");
    assert.deepEqual(await svc.bucket.keys(), []);
    // An expired share is no share: whoever writes to its id next makes it.
    assert.equal((await putPack(svc, { ...newShare(), id: share.id }, packed(BUNDLE).packs[0])).status, 201);
  });
});

describe("a pack's read", () => {
  test("answers the sealed pack, kept as immutable, while the share's manifest lives", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [pack] } = await shared(svc, share, BUNDLE);
    const { key } = await derived(share.id);
    const read = await svc.call("GET", `/v1/shares/${share.id}/packs/${pack.id}`);
    assert.equal(read.status, 200);
    assert.equal(read.headers.get("Content-Type"), "application/octet-stream");
    assert.equal(read.headers.get("Cache-Control"), "private, max-age=604800, immutable");
    assert.equal(read.headers.get("Content-Length"), String(pack.bytes.byteLength + SEALING));
    assert.deepEqual(await unseal(key, await read.arrayBuffer(), `cad-share/2 pack ${pack.id}`), pack.bytes);
    const head = await svc.call("HEAD", `/v1/shares/${share.id}/packs/${pack.id}`);
    assert.equal(head.status, 200);
    assert.equal(head.body, null);
    assert.equal(head.headers.get("Cache-Control"), read.headers.get("Cache-Control"));
  });

  test("is 404 without a live manifest (an expired one deletes the share) or for a pack it lacks, and 400 for a bad pack id", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [pack], files } = packed(BUNDLE);
    assert.equal((await putPack(svc, share, pack)).status, 201);
    await refusal(await svc.call("GET", `/v1/shares/${share.id}/packs/${pack.id}`), 404, "not_found");
    assert.equal((await commit(svc, share, manifestOf(files))).status, 201);
    assert.equal((await svc.call("GET", `/v1/shares/${share.id}/packs/${pack.id}`)).status, 200);
    await refusal(await svc.call("GET", `/v1/shares/${share.id}/packs/${sha256("no such pack")}`), 404, "not_found");
    await refusal(await svc.call("GET", `/v1/shares/${share.id}/packs/${pack.id.slice(2)}`), 400, "bad_pack_id");
    await refusal(await svc.call("GET", `/v1/shares/${share.id.slice(1)}/packs/${pack.id}`), 400, "bad_id");
    svc.time.at += 7 * DAY;
    await refusal(await svc.call("GET", `/v1/shares/${share.id}/packs/${pack.id}`), 404, "not_found");
    assert.deepEqual(await svc.bucket.keys(), []);
  });
});

describe("a delete", () => {
  for (const which of ["delete", "write"]) {
    test(`with the ${which} secret deletes every object of the share (204); then there is none (404)`, async () => {
      const svc = service({ pageSize: 2 });
      const share = newShare();
      const kept = newShare();
      await shared(svc, kept, BUNDLE);
      await shared(svc, share, BUNDLE, [["b.json", "{}"]], [["c.json", "{}"]]);
      const deleted = await remove(svc, share, share[which]);
      assert.equal(deleted.status, 204);
      assert.equal(deleted.body, null);
      assert.deepEqual(await held(svc, share.id), []);
      assert.equal((await held(svc, kept.id)).length, 3, "another share is left as it was");
      await refusal(await svc.call("GET", `/v1/shares/${share.id}`), 404, "not_found");
      await refusal(await remove(svc, share, share[which]), 404, "not_found");
    });
  }

  test("of a share with packs and no manifest deletes them (204)", async () => {
    const svc = service();
    const share = newShare();
    assert.equal((await putPack(svc, share, packed(BUNDLE).packs[0])).status, 201);
    assert.equal((await remove(svc, share)).status, 204);
    assert.deepEqual(await svc.bucket.keys(), []);
  });

  test("with a secret that matches neither hash is 403, without one 401, a malformed one 400, of no share 404", async () => {
    const svc = service();
    const share = newShare();
    await shared(svc, share, BUNDLE);
    await refusal(await remove(svc, share, newShare().delete), 403, "forbidden");
    const unauthorized = await svc.call("DELETE", `/v1/shares/${share.id}`);
    await refusal(unauthorized, 401, "unauthorized");
    assert.equal(unauthorized.headers.get("WWW-Authenticate"), "Bearer");
    await refusal(await remove(svc, share, "short"), 400, "bad_secret");
    await refusal(await svc.call("DELETE", "/v1/shares/bad", { headers: { Authorization: `Bearer ${share.delete}` } }), 400, "bad_id");
    await refusal(await remove(svc, newShare()), 404, "not_found");
    assert.equal((await svc.call("GET", `/v1/shares/${share.id}`)).status, 200);
  });
});

describe("two shares", () => {
  test("are apart: neither's packs can be read, written or named through the other", async () => {
    const svc = service();
    const one = newShare();
    const two = newShare();
    const { packs: [mine] } = await shared(svc, one, BUNDLE);
    const { packs: [theirs], files } = await shared(svc, two, [["manifest.json", '{"two":1}']]);
    await refusal(await svc.call("GET", `/v1/shares/${two.id}/packs/${mine.id}`), 404, "not_found");
    await refusal(await putPack(svc, { ...two, id: one.id }, theirs), 403, "forbidden");
    await refusal(await commit(svc, { ...two, id: one.id }, manifestOf(files)), 403, "forbidden");
    const named = await refusal(await commit(svc, two, manifestOf(packed(BUNDLE).files)), 409, "missing_packs");
    assert.deepEqual(named.missing, [mine.id]);

    const [a, b] = [await derived(one.id), await derived(two.id)];
    assert.notEqual(a.prefix, b.prefix);
    const stored = await (await svc.bucket.get(`${a.prefix}p/${mine.id}`)).arrayBuffer();
    await assert.rejects(unseal(b.key, stored, `cad-share/2 pack ${mine.id}`), "one share's key opens nothing of another's");
    assert.deepEqual(await openShare(svc, one.id), Object.fromEntries(BUNDLE));
  });
});

describe("the bucket's lifecycle rule", () => {
  test("takes nothing a live share keeps: a commit stores again, unchanged, what the rule would delete before it expires", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [p1, p2], files } = await shared(svc, share, BUNDLE, [["b.json", '"b"']]);
    const { prefix } = await derived(share.id);
    const object = (name) => svc.bucket.head(`${prefix}${name}`);
    const bytesOf = async (name) => new Uint8Array(await (await svc.bucket.get(`${prefix}${name}`)).arrayBuffer());

    // Within the day the rule's 8 days leave past the 7: nothing to store again.
    svc.time.at += DAY / 2;
    assert.equal((await commit(svc, share, manifestOf(files))).status, 200);
    for (const name of ["owner", `p/${p1.id}`, `p/${p2.id}`]) assert.equal((await object(name)).uploaded.getTime(), START, name);

    // Six days on, the commit keeps the owner and p1, uploaded on day 0, past the rule's day 8.
    svc.time.at = START + 6 * DAY;
    const before = { owner: await object("owner"), p1: await bytesOf(`p/${p1.id}`) };
    const edited = packed([["b.json", '"b, edited"']]);
    assert.equal((await putPack(svc, share, edited.packs[0])).status, 201);
    assert.equal((await commit(svc, share, manifestOf({ ...files, ...edited.files }))).status, 200);
    const owner = await object("owner");
    assert.equal(owner.uploaded.getTime(), svc.now());
    assert.deepEqual(owner.customMetadata, before.owner.customMetadata);
    assert.equal((await object(`p/${p1.id}`)).uploaded.getTime(), svc.now());
    assert.deepEqual(await bytesOf(`p/${p1.id}`), before.p1);
    // p2 is the replaced manifest's alone, kept for a page already open: not stored again.
    assert.equal((await object(`p/${p2.id}`)).uploaded.getTime(), START);

    svc.time.at = START + 8 * DAY + DAY / 2;
    await lifecycle(svc);
    assert.deepEqual(await held(svc, share.id), ["manifest", "owner", `p/${edited.packs[0].id}`, `p/${p1.id}`].sort());
    svc.time.at = START + 13 * DAY - 1;
    assert.deepEqual(await openShare(svc, share.id), { ...Object.fromEntries(BUNDLE), "b.json": '"b, edited"' });
    assert.equal((await remove(svc, share)).status, 204, "the owner is there to delete it");
  });

  test("takes none of the packs a live share's files name either", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [bundle], files: view } = packed(BUNDLE);
    const code = packOf(gz("print('juno')\n"));
    const manifest = manifestOf(view, { files: { "juno.py": entryOf("print('juno')\n", code.at[0]) }, entry: "juno.py", made: MADE });
    for (const pack of [bundle, code]) assert.equal((await putPack(svc, share, pack)).status, 201);
    assert.equal((await commit(svc, share, manifest)).status, 201);
    svc.time.at = START + 6 * DAY;
    assert.equal((await commit(svc, share, manifest)).status, 200);
    const { prefix } = await derived(share.id);
    assert.equal((await svc.bucket.head(`${prefix}p/${code.id}`)).uploaded.getTime(), svc.now(), "stored again, ahead of the rule");
    svc.time.at = START + 8 * DAY + DAY / 2;
    await lifecycle(svc);
    assert.deepEqual(await held(svc, share.id), ["manifest", "owner", `p/${bundle.id}`, `p/${code.id}`].sort());
    assert.deepEqual(await openShare(svc, share.id, "files"), { "juno.py": "print('juno')\n" });
  });
});

describe("the rate limits", () => {
  test("count commits and deletes in LIMITER, packs in LIMITER_PACKS, by the client's address, and refuse past them (429)", async () => {
    const counted = { LIMITER: [], LIMITER_PACKS: [] };
    const allow = { LIMITER: true, LIMITER_PACKS: true };
    const limiterOf = (name) => ({ async limit({ key }) { counted[name].push(key); return { success: allow[name] }; } });
    const svc = service({ limiter: limiterOf("LIMITER"), packLimiter: limiterOf("LIMITER_PACKS") });
    const share = newShare();
    const { packs: [pack], files } = await shared(svc, share, BUNDLE);
    assert.equal((await svc.call("GET", `/v1/shares/${share.id}`)).status, 200);
    assert.equal((await svc.call("GET", `/v1/shares/${share.id}/packs/${pack.id}`)).status, 200);
    assert.deepEqual(counted, { LIMITER: [ADDRESS], LIMITER_PACKS: [ADDRESS] }, "a read is not counted");

    allow.LIMITER_PACKS = false;
    const refusedPack = await putPack(svc, share, pack);
    await refusal(refusedPack, 429, "rate_limited");
    assert.equal(refusedPack.headers.get("Retry-After"), "60");
    assert.equal((await commit(svc, share, manifestOf(files))).status, 200, "a commit is counted apart");

    allow.LIMITER = false;
    await refusal(await commit(svc, share, manifestOf(files)), 429, "rate_limited");
    const refusedDelete = await remove(svc, share);
    await refusal(refusedDelete, 429, "rate_limited");
    assert.equal(refusedDelete.headers.get("Retry-After"), "60");
    assert.deepEqual(counted, { LIMITER: Array(4).fill(ADDRESS), LIMITER_PACKS: [ADDRESS, ADDRESS] });
    assert.equal((await svc.call("GET", `/v1/shares/${share.id}`)).status, 200, "nothing was deleted");
  });
});

describe("what the service keeps", () => {
  test("is sealed bytes and hashes under the name the id derives: never the id, the key or a secret", async () => {
    const svc = service();
    const share = newShare();
    const { packs } = await shared(svc, share, BUNDLE, [["b.json", "{}"]]);
    const { keyBytes, prefix } = await derived(share.id);
    const keys = await svc.bucket.keys();
    assert.ok(keys.length > 0 && keys.every((key) => key.startsWith(prefix)));
    const secrets = [share.id, share.write, share.delete, hex(keyBytes), b64url(keyBytes)];
    for (const key of keys) {
      const object = await svc.bucket.get(key);
      const stored = Buffer.from(await object.arrayBuffer());
      const kept = `${key} ${JSON.stringify(object.customMetadata)} ${JSON.stringify(object.httpMetadata)} ${stored.toString("latin1")}`;
      for (const value of secrets) assert.ok(!kept.includes(value), key);
      assert.ok(!stored.includes(Buffer.from(keyBytes)), key);
      for (const pack of packs) assert.ok(!stored.includes(Buffer.from(pack.bytes)), `${key} keeps a pack in the clear`);
    }
  });
});

describe("the rest of the API", () => {
  test("another method is 405 with Allow, another path 404, and nothing answers with CORS", async () => {
    const svc = service();
    const share = newShare();
    const pack = sha256("a pack");
    const options = await svc.call("OPTIONS", `/v1/shares/${share.id}`, {
      headers: { Origin: "https://elsewhere.test", "Access-Control-Request-Method": "PUT" },
    });
    await refusal(options, 405, "method_not_allowed");
    assert.equal(options.headers.get("Allow"), "PUT, GET, HEAD, DELETE");
    await refusal(await svc.call("POST", `/v1/shares/${share.id}`), 405, "method_not_allowed");
    const packMethod = await svc.call("DELETE", `/v1/shares/${share.id}/packs/${pack}`);
    await refusal(packMethod, 405, "method_not_allowed");
    assert.equal(packMethod.headers.get("Allow"), "PUT, GET, HEAD");
    for (const path of ["/v1", "/v1/other", `/v1/shares/${share.id}/`, `/v1/shares/${share.id}/packs`, `/v1/shares/${share.id}/packs/${pack}/x`]) {
      await refusal(await svc.call("GET", path), 404, "not_found");
    }
    await shared(svc, share, BUNDLE);
    await svc.call("GET", `/v1/shares/${share.id}`, { headers: { Origin: "https://elsewhere.test" } });
  });
});

/** A model's share as the command makes one: its view, then the files that made it, after the view's in the
 * same pack and on into more, one file's member split over three packs and one member named twice; and a pack
 * the view alone names. Its manifest and packs, and each file's content and member. */
function modelShare({ name = "juno" } = {}) {
  const contents = {
    "juno.py": "import lib.head\nprint('juno')\n",
    "lib/head.py": "HEAD = 1\n",
    "lib/empty.py": "",
    "modèle/pièce.py": "# é\n",
    "same.py": "same\n",
    "again.py": "same\n",
    "manifest.json": '{"files":"not the view\'s"}',
    "inputs/big.bin": randomBytes(150_000),
  };
  const members = Object.fromEntries(Object.entries(contents).map(([path, content]) => [path, gz(content)]));
  const big = members["inputs/big.bin"];
  const cut = Math.ceil(big.length / 3);
  const first = packOf(gz(BUNDLE[0][1]), gz(BUNDLE[1][1]), members["juno.py"]);
  const viewOnly = packOf(gz("a part's mesh"));
  const second = packOf(members["lib/head.py"], members["lib/empty.py"], members["modèle/pièce.py"], members["same.py"],
                        members["manifest.json"], big.subarray(0, cut));
  const third = packOf(big.subarray(cut, 2 * cut));
  const fourth = packOf(big.subarray(2 * cut));
  const view = {
    "manifest.json": entryOf(BUNDLE[0][1], first.at[0]),
    "structure.json": entryOf(BUNDLE[1][1], first.at[1]),
    "parts/a/mesh.xbm": entryOf("a part's mesh", viewOnly.at[0]),
  };
  const files = {
    "juno.py": entryOf(contents["juno.py"], first.at[2]),
    "lib/head.py": entryOf(contents["lib/head.py"], second.at[0]),
    "lib/empty.py": entryOf("", second.at[1]),
    "modèle/pièce.py": entryOf(contents["modèle/pièce.py"], second.at[2]),
    "same.py": entryOf("same\n", second.at[3]),
    "again.py": entryOf("same\n", second.at[3]),
    "manifest.json": entryOf(contents["manifest.json"], second.at[4]),
    "inputs/big.bin": entryOf(contents["inputs/big.bin"], second.at[5], third.at[0], fourth.at[0]),
  };
  return {
    contents, members, view, files, viewOnly,
    packs: [first, viewOnly, second, third, fourth],
    filesPacks: [first, second, third, fourth].map((pack) => pack.id),
    manifest: manifestOf(view, { name, files, entry: "juno.py", made: MADE }),
  };
}

async function sharedModel(svc, share, model = modelShare()) {
  for (const pack of model.packs) assert.equal((await putPack(svc, share, pack)).status, 201);
  const committed = await commit(svc, share, model.manifest);
  assert.ok(committed.status === 200 || committed.status === 201);
  return model;
}

const byBytes = (a, b) => Buffer.compare(Buffer.from(a), Buffer.from(b));

describe("the files' zip", () => {
  test("holds every one of the files, sorted by path under one folder named for the share, and nothing of the view", async () => {
    const svc = service({ Bucket: Counting });
    const share = newShare();
    const model = await sharedModel(svc, share);
    svc.bucket.gets.length = 0;
    const { entries } = await zipOfShare(svc, share.id);

    const paths = Object.keys(model.contents).sort(byBytes);
    assert.deepEqual(entries.map((entry) => entry.name), ["juno/", ...paths.map((path) => `juno/${path}`)]);
    const [folder, ...files] = entries;
    assert.equal(folder.folder, true);
    assert.deepEqual([folder.method, folder.size, folder.compressed, folder.crc, folder.flags], [0, 0, 0, 0, 0x800]);
    assert.deepEqual([folder.mode, folder.dos, folder.system], [0o40755, 0x10, 3]);
    assert.deepEqual(folder.time, [1980, 1, 1, 0, 0, 0]);
    for (const [index, path] of paths.entries()) {
      const entry = files[index];
      assertFileEntry(entry, { content: model.contents[path] });
      // The member's own deflate stream, as it lies in its packs, with its trailer's CRC-32 and size.
      const member = model.members[path];
      assert.equal(entry.compressed, member.length - 18, path);
      assert.equal(entry.raw, sha256(member.subarray(10, -8)), path);
      assert.equal(entry.crc, member.readUInt32LE(member.length - 8), path);
      assert.deepEqual([entry.needs, entry.local.needs, entry.version, entry.local.extra], [20, 20, 20, ""], path);
      assert.deepEqual([entry.local.compressed, entry.local.size], [entry.compressed, entry.size], path);
    }
    assert.notEqual(Buffer.from(files[paths.indexOf("manifest.json")].data, "base64").toString(), BUNDLE[0][1], "the files' manifest.json, not the view's");

    // It read the manifest and the packs the files name, and never the pack the view alone names.
    const { prefix } = await derived(share.id);
    assert.equal(svc.bucket.gets[0], `${prefix}manifest`);
    const read = new Set(svc.bucket.gets.slice(1).map((key) => key.slice(`${prefix}p/`.length)));
    assert.deepEqual([...read].sort(), [...model.filesPacks].sort());
  });

  test("answers as a download named for the share, with its entry and what made it, never kept; HEAD the same, with no zip", async () => {
    const svc = service();
    const share = newShare();
    const model = await sharedModel(svc, share);
    const expected = {
      "Content-Type": "application/zip",
      "Content-Disposition": 'attachment; filename="juno.zip"',
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Cad-Share-Entry": "juno.py",
      "Cad-Share-Made": "cad=0.11.17, build123d=0.13.0, OCP=8.0.1.1.0, python=3.13.18, system=Linux, arch=x86_64",
    };
    const zip = await svc.call("GET", `/${share.id}.zip`);
    const head = await svc.call("HEAD", `/${share.id}.zip`);
    for (const answer of [zip, head]) {
      assert.equal(answer.status, 200);
      for (const [name, value] of Object.entries(expected)) assert.equal(answer.headers.get(name), value, name);
    }
    assert.equal(head.body, null);
    assert.equal(new DataView(await zip.arrayBuffer()).getUint32(0, true), 0x04034b50);

    // What would not travel in a header as it is goes percent-encoded, UTF-8, and a percent-decoder reads it back.
    const odd = { cad: "0.11.17+local", "a note": "x, y=z 100%", "é": "ü" };
    const entry = "modèle/pièce.py";
    assert.equal((await commit(svc, share, { ...model.manifest, entry, made: odd })).status, 200);
    const encoded = await svc.call("HEAD", `/${share.id}.zip`);
    assert.equal(encoded.headers.get("Cad-Share-Entry"), "mod%C3%A8le/pi%C3%A8ce.py");
    assert.equal(encoded.headers.get("Cad-Share-Made"), "cad=0.11.17+local, a%20note=x%2C%20y%3Dz%20100%25, %C3%A9=%C3%BC");
    assert.equal(decodeURIComponent(encoded.headers.get("Cad-Share-Entry")), entry);
    assert.deepEqual(Object.fromEntries(encoded.headers.get("Cad-Share-Made").split(", ").map((member) => member.split("=").map(decodeURIComponent))), odd);

    // A file document's has no entry and nothing that made it: neither header. Nor has an empty made.
    for (const made of [null, {}]) {
      assert.equal((await commit(svc, share, { ...model.manifest, entry: null, made })).status, 200);
      const document = await svc.call("HEAD", `/${share.id}.zip`);
      assert.equal(document.status, 200);
      assert.equal(document.headers.get("Cad-Share-Entry"), null);
      assert.equal(document.headers.get("Cad-Share-Made"), null);
    }
  });

  test("names its file and its folder for the share, made safe", async () => {
    const svc = service();
    const share = newShare();
    const model = await sharedModel(svc, share);
    const names = [
      ["Bracket (v2).step", "Bracket__v2_.step"], ["../../etc/passwd", "_.._etc_passwd"], ["..", "share"], [".", "share"],
      ["...hidden.", "hidden"], ["模型 🙂", "____"], ["x".repeat(150), "x".repeat(100)], [`${"a".repeat(99)}.b`, "a".repeat(99)],
    ];
    for (const [name, safe] of names) {
      assert.equal((await commit(svc, share, { ...model.manifest, name })).status, 200);
      const head = await svc.call("HEAD", `/${share.id}.zip`);
      assert.equal(head.headers.get("Content-Disposition"), `attachment; filename="${safe}.zip"`, name);
      if (name.startsWith(".")) {
        const { entries } = await zipOfShare(svc, share.id, "names");
        assert.ok(entries.every((entry) => entry.startsWith(`${safe}/`)), name);
      }
    }
  });

  test("of a share with no files is a zip of an empty folder", async () => {
    const svc = service({ Bucket: Counting });
    const share = newShare();
    const { files: view } = await shared(svc, share, BUNDLE);
    await commit(svc, share, manifestOf(view, { name: "bracket" }));
    svc.bucket.gets.length = 0;
    const { bytes, entries } = await zipOfShare(svc, share.id);
    assert.deepEqual(entries.map((entry) => [entry.name, entry.folder, entry.size, entry.mode]), [["bracket/", true, 0, 0o40755]]);
    assert.equal(bytes.byteLength, (30 + 8) + (46 + 8) + 22, "a folder's local header, its directory record, the end");
    assert.equal(svc.bucket.gets.length, 1, "the manifest alone is read");
  });

  test("stores a member not of the plain form inflated (method 0), its CRC-32 computed, whole in a pack or split", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [bundle], files: view } = packed(BUNDLE);
    const contents = { "named.py": "print('named')\n", "extra.py": `# ${"x".repeat(5000)}\n`, "plain.py": "plain = 1\n" };
    const named = unplain(contents["named.py"]);
    const extra = unplain(contents["extra.py"], { name: null, extra: [1, 2, 3, 4] });
    const one = packOf(named, extra.subarray(0, 20));
    const two = packOf(extra.subarray(20), gz(contents["plain.py"]));
    const files = {
      "named.py": entryOf(contents["named.py"], one.at[0]),
      "extra.py": entryOf(contents["extra.py"], one.at[1], two.at[0]),
      "plain.py": entryOf(contents["plain.py"], two.at[1]),
    };
    for (const pack of [bundle, one, two]) assert.equal((await putPack(svc, share, pack)).status, 201);
    assert.equal((await commit(svc, share, manifestOf(view, { files, entry: "plain.py", made: MADE }))).status, 201);
    const { entries } = await zipOfShare(svc, share.id);
    assert.deepEqual(entries.map((entry) => [entry.name, entry.method]), [["juno/", 0], ["juno/extra.py", 0], ["juno/named.py", 0], ["juno/plain.py", 8]]);
    for (const entry of entries.slice(1, 3)) {
      const content = contents[entry.name.slice("juno/".length)];
      assertFileEntry(entry, { content, method: 0 });
      assert.equal(entry.compressed, entry.size);
      assert.equal(entry.raw, sha256(content), "stored as it is");
    }
  });

  test("writes Zip64 where a file's size needs it: both sizes in its local header's extra field, the size in its record's", async () => {
    const svc = service();
    const share = newShare();
    const { packs: [bundle], files: view } = packed(BUNDLE);
    // A member of five bytes whose entry says 4 GiB and five: its trailer's size, modulo 2^32, agrees.
    const huge = gz("hello");
    const pack = packOf(huge, gz("x = 1\n"));
    const files = { "huge.bin": { ...entryOf("hello", pack.at[0]), bytes: 2 ** 32 + 5 }, "small.py": entryOf("x = 1\n", pack.at[1]) };
    for (const each of [bundle, pack]) assert.equal((await putPack(svc, share, each)).status, 201);
    assert.equal((await commit(svc, share, manifestOf(view, { files, entry: "small.py", made: MADE }))).status, 201);
    const { entries } = await zipOfShare(svc, share.id, "headers");
    const [, big, small] = entries;
    assert.equal(big.name, "juno/huge.bin");
    assert.deepEqual([big.size, big.compressed, big.needs, big.version, big.local.needs], [2 ** 32 + 5, huge.length - 18, 45, 45, 45]);
    assert.deepEqual([big.local.size, big.local.compressed], [0xFFFFFFFF, 0xFFFFFFFF]);
    const extra = Buffer.from(big.local.extra, "hex");
    assert.deepEqual([extra.readUInt16LE(0), extra.readUInt16LE(2), Number(extra.readBigUInt64LE(4)), Number(extra.readBigUInt64LE(12))],
                     [1, 16, 2 ** 32 + 5, huge.length - 18]);
    assert.equal(big.raw, sha256(huge.subarray(10, -8)));
    assert.deepEqual([small.needs, small.local.extra, small.size], [20, "", 6], "a file that fits takes none");
  });

  test("writes Zip64 where the count needs it: from 65,535 entries, the count in its own end record", async () => {
    const pack = packOf(gz("same\n"));
    const files = (count) => Array.from({ length: count }, (_, index) => [`f/${String(index).padStart(5, "0")}.txt`, entryOf("same\n", pack.at[0])]);
    const zipped = async (count) => new Uint8Array(await new Response(zipOf("many", files(count), async () => pack.bytes)).arrayBuffer());

    // 65,533 files and their folder fit the end record's two bytes.
    const fits = endOf(await zipped(0xFFFD));
    assert.deepEqual([fits.end.count, fits.zip64], [0xFFFE, null]);
    // 65,534 and their folder: 0xFFFF entries, which the field holds only as its "see Zip64".
    const bytes = await zipped(0xFFFE);
    const { end, zip64 } = endOf(bytes);
    assert.equal(end.count, 0xFFFF);
    assert.deepEqual(zip64, { count: 0xFFFF, size: end.size, offset: end.offset });
    const names = readZip(bytes, "names");
    assert.equal(names.length, 0xFFFF);
    assert.deepEqual([names[0], names[1], names.at(-1)], ["many/", "many/f/00000.txt", "many/f/65533.txt"]);
  });

  test("with Zip64's limits lowered writes every Zip64 record, and a reader reads the zip whole by them", async () => {
    const model = modelShare();
    const packs = new Map(model.packs.map((pack) => [pack.id, pack.bytes]));
    const stream = zipOf("juno", Object.entries(model.files), async (pack) => packs.get(pack), { size: 0, count: 0 });
    const bytes = new Uint8Array(await new Response(stream).arrayBuffer());
    const entries = readZip(bytes);
    const paths = Object.keys(model.contents).sort(byBytes);
    assert.deepEqual(entries.map((entry) => entry.name), ["juno/", ...paths.map((path) => `juno/${path}`)]);
    for (const [index, path] of paths.entries()) {
      const entry = entries[index + 1];
      assertFileEntry(entry, { content: model.contents[path] });
      assert.equal(entry.raw, sha256(model.members[path].subarray(10, -8)), path);
      assert.deepEqual([entry.needs, entry.local.needs, entry.local.size, entry.local.compressed], [45, 45, 0xFFFFFFFF, 0xFFFFFFFF], path);
      assert.equal(entry.local.extra.length, 2 * 20, path);
    }
    assert.ok(entries.slice(1).every((entry, index) => entry.offset > entries[index].offset), "each found at its own offset");
    const { end, zip64 } = endOf(bytes);
    assert.deepEqual(end, { count: 0xFFFF, size: 0xFFFFFFFF, offset: 0xFFFFFFFF });
    assert.equal(zip64.count, entries.length);
    assert.equal(zip64.offset + zip64.size, bytes.byteLength - 22 - 20 - 56);
    assert.deepEqual(ZIP64, { size: 0xFFFFFFFF, count: 0xFFFF });
  });

  test("is 404 where the share has no live manifest, as its other reads are; its route is GET and HEAD of an id's zip", async () => {
    const svc = service();
    const share = newShare();
    await refusal(await svc.call("GET", `/${share.id}.zip`), 404, "not_found");
    await refusal(await svc.call("HEAD", `/${share.id}.zip`), 404, "not_found");
    await sharedModel(svc, share);
    for (const method of ["PUT", "POST", "DELETE"]) {
      const answer = await svc.call(method, `/${share.id}.zip`);
      await refusal(answer, 405, "method_not_allowed");
      assert.equal(answer.headers.get("Allow"), "GET, HEAD");
    }
    for (const path of ["/short.zip", `/${share.id}.ZIP`, `/${share.id}.zip/`, `/${share.id}/files.zip`, `/${share.id}.zip.zip`]) {
      await refusal(await svc.call("GET", path), 404, "not_found");
    }
    assert.equal((await remove(svc, share)).status, 204);
    await refusal(await svc.call("GET", `/${share.id}.zip`), 404, "not_found");

    // Past its expiry: the share deleted whole.
    const later = newShare();
    await sharedModel(svc, later);
    svc.time.at += 7 * DAY;
    await refusal(await svc.call("GET", `/${later.id}.zip`), 404, "not_found");
    assert.deepEqual(await svc.bucket.keys(), []);

    // A manifest of the bundle alone, as one was before it carried the files that made it, has none to give.
    const earlier = newShare();
    const { files: view } = await shared(svc, earlier, BUNDLE);
    const { keyBytes, prefix } = await derived(earlier.id);
    const key = await webcrypto.subtle.importKey("raw", keyBytes, "AES-GCM", false, ["encrypt"]);
    const metadata = (await svc.bucket.head(`${prefix}manifest`)).customMetadata;
    await svc.bucket.put(`${prefix}manifest`, await seal(key, utf8(JSON.stringify({ format: FORMAT, files: view })), "cad-share/2 manifest"),
                         { customMetadata: metadata });
    await refusal(await svc.call("GET", `/${earlier.id}.zip`), 404, "not_found");
    assert.equal((await svc.call("GET", `/v1/shares/${earlier.id}`)).status, 200);
  });

  test("counts as a pack in LIMITER_PACKS, by the client's address, and is refused past it (429)", async () => {
    const counted = [];
    const allow = { packs: true };
    const packLimiter = { async limit({ key }) { counted.push(key); return { success: allow.packs }; } };
    const svc = service({ packLimiter });
    const share = newShare();
    const model = await sharedModel(svc, share);
    counted.length = 0;
    assert.equal((await svc.call("GET", `/${share.id}.zip`)).status, 200);
    assert.equal((await svc.call("HEAD", `/${share.id}.zip`)).status, 200);
    assert.equal((await svc.call("GET", `/v1/shares/${share.id}/packs/${model.packs[0].id}`)).status, 200);
    assert.deepEqual(counted, [ADDRESS, ADDRESS], "a zip is counted, a pack's read is not");
    allow.packs = false;
    for (const method of ["GET", "HEAD"]) {
      const refused = await svc.call(method, `/${share.id}.zip`);
      await refusal(refused, 429, "rate_limited");
      assert.equal(refused.headers.get("Retry-After"), "60");
    }
    await refusal(await putPack(svc, share, model.packs[0]), 429, "rate_limited");
  });

  test("fails part way, and never ends as a whole zip, where a pack its files name is gone or a member does not inflate", async () => {
    const svc = service();
    const share = newShare();
    const model = await sharedModel(svc, share);
    const { prefix } = await derived(share.id);
    await svc.bucket.delete(`${prefix}p/${model.filesPacks.at(-1)}`);
    const cut = await svc.call("GET", `/${share.id}.zip`);
    assert.equal(cut.status, 200);
    await assert.rejects(cut.arrayBuffer());

    const broken = newShare();
    const { packs: [bundle], files: view } = packed(BUNDLE);
    const member = unplain("print(1)\n");
    const pack = packOf(member.subarray(0, member.length - 3));
    for (const each of [bundle, pack]) assert.equal((await putPack(svc, broken, each)).status, 201);
    const files = { "juno.py": entryOf("print(1)\n", pack.at[0]) };
    assert.equal((await commit(svc, broken, manifestOf(view, { files, entry: "juno.py", made: MADE }))).status, 201);
    const failed = await svc.call("GET", `/${broken.id}.zip`);
    assert.equal(failed.status, 200);
    await assert.rejects(failed.arrayBuffer());
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
    const svc = service();
    for (const method of ["GET", "HEAD"]) {
      const response = await svc.call(method, "/");
      assert.equal(response.status, 302);
      assert.equal(response.headers.get("Location"), HOME);
    }
    await refusal(await svc.call("POST", "/"), 405, "method_not_allowed");
  });

  test("a share's path answers the viewer's index.html with the page's security headers, share or no share", async () => {
    const svc = service();
    const response = await svc.call("GET", `/${newShare().id}`);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), INDEX);
    assertPageHeaders(response);
    const head = await svc.call("HEAD", `/${newShare().id}`);
    assert.equal(head.status, 200);
    assert.equal(head.body, null);
    assertPageHeaders(head);
    await refusal(await svc.call("PUT", `/${newShare().id}`), 405, "method_not_allowed");
    const bare = service({ ASSETS: localAssets(join(assetsDir, "assets")) }); // a folder with no index.html
    await refusal(await bare.call("GET", `/${newShare().id}`), 404, "not_found");
  });

  test("the viewer's own files are served, HTML with the page's headers, and anything else is 404", async () => {
    const svc = service();
    const index = await svc.call("GET", "/index.html");
    assert.equal(index.status, 200);
    assertPageHeaders(index);
    const revalidated = await svc.call("GET", "/index.html", { headers: { "If-None-Match": index.headers.get("ETag") ?? "*" } });
    assert.equal(revalidated.status, 200, "an HTML answer is whole, to hash its scripts");
    assert.equal(await revalidated.text(), INDEX);
    const script = await svc.call("GET", "/assets/app.js");
    assert.equal(script.status, 200);
    assert.match(script.headers.get("Content-Type"), /^text\/javascript/);
    assert.equal(script.headers.get("X-Content-Type-Options"), "nosniff");
    assert.equal(await script.text(), "export {};\n");
    const scriptHead = await svc.call("HEAD", "/assets/app.js");
    assert.equal(scriptHead.status, 200);
    assert.equal(scriptHead.body, null);
    await refusal(await svc.call("GET", "/assets/missing.js"), 404, "not_found");
    await refusal(await svc.call("GET", `/${newShare().id}/`), 404, "not_found");
    await refusal(await svc.call("GET", "/assets/%2e%2e/%2e%2e/package.json"), 404, "not_found");
  });
});
