import assert from 'node:assert/strict';
import { createHash, webcrypto } from 'node:crypto';
import test from 'node:test';
import { gzipSync } from 'node:zlib';
import { deriveShareBits, isShareSecret, openShare, readShareAddress,
  SHARE_DAMAGED, SHARE_PREFETCH, SHARE_UNAVAILABLE, SHARE_UNSUPPORTED } from './share.js';

const encode = value => new TextEncoder().encode(typeof value === 'string' ? value : JSON.stringify(value));
const hex = bytes => Buffer.from(bytes).toString('hex');
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
/** A fresh ArrayBuffer of `bytes` alone, as a response's body is. */
const body = bytes => new Uint8Array(bytes).buffer;
const newId = () => Buffer.from(webcrypto.getRandomValues(new Uint8Array(16))).toString('base64url');
/** Bytes no compression shrinks, the same each run: `length` of them from `seed`. */
function noise(length, seed) {
  const bytes = new Uint8Array(length);
  let state = seed * 2654435761 >>> 0 || 1;
  for (let index = 0; index < length; index += 1) {
    state ^= state << 13; state ^= state >>> 17; state ^= state << 5; state >>>= 0;
    bytes[index] = state & 0xff;
  }
  return bytes;
}

// The vectors every piece of sharing is checked against (computed with Web Crypto, the HKDF half checked with
// Python's hmac).
const VECTORS = {
  id: '0sHbv5_DYsmyh0xEOGyhAw',
  key: 'bf9fb149a034b6d5702170bbbab7409bdf0454963ddd6cdce46bf73006310fe6',
  name: '38d4a8b66f195cc29d2775a039a5623334ff97adfa483315e6a881affa311744',
  manifest: '{"format":"cad-share/2","files":{}}',
  manifestSealed: '0000000000000000000000001805bb723d8d97c83c5276bc082386bfa6fb1c0f261cab97e775011c9ba9236e4a7453650be41051cebe7d4be9d018a48bf8cf',
  pack: 'pack bytes',
  packId: 'd61037e21c7e5fc5318069739439f61ccea49f6b11a1dad1ecf15cb0d831e680',
  packSealed: '0000000000000000000000001346be766f828fc87b1b4228fcd3958832a517117534968df561',
};

/** The key a share's service seals it with: HKDF-SHA256 of its id, made here as the service makes it. */
async function sealingKey(id) {
  const input = await webcrypto.subtle.importKey('raw', encode(id), 'HKDF', false, ['deriveBits']);
  const raw = await webcrypto.subtle.deriveBits({ name: 'HKDF', hash: 'SHA-256', salt: encode('cad-share/2'), info: encode('key') }, input, 256);
  return webcrypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt']);
}
/** `plain` sealed as the service seals an object of share `id`: `IV || AES-256-GCM(key, IV, plain, aad)`. */
async function seal(id, plain, aad, iv = webcrypto.getRandomValues(new Uint8Array(12))) {
  const sealed = await webcrypto.subtle.encrypt({ name: 'AES-GCM', iv, additionalData: encode(aad) }, await sealingKey(id), plain);
  return Buffer.concat([iv, new Uint8Array(sealed)]);
}

/**
 * A share of `files` (path to bytes, in reading order) as the command packs one and the service seals it: each
 * file's gzip member back to back in packs closed at `packBytes` (a member that does not fit the room left goes on
 * into the next pack), or in a pack of its own each (`each`); each pack named by its SHA-256; the manifest naming
 * every file's ranges.
 */
async function makeShare(files, { packBytes = 4 << 20, each = false, id = newId() } = {}) {
  const packs = [];
  let open = [];
  let used = 0;
  const close = () => { if (used) packs.push(Buffer.concat(open)); open = []; used = 0; };
  const placed = {};
  for (const [path, bytes] of Object.entries(files)) {
    const member = gzipSync(bytes);
    const at = [];
    for (let offset = 0; offset < member.length;) {
      if (used === packBytes) close();
      const length = Math.min(packBytes - used, member.length - offset);
      at.push([packs.length, used, length]);
      open.push(member.subarray(offset, offset + length));
      used += length;
      offset += length;
    }
    placed[path] = { sha256: sha256(bytes), bytes: bytes.length, at };
    if (each) close();
  }
  close();
  const ids = packs.map(sha256);
  for (const entry of Object.values(placed)) entry.at = entry.at.map(([index, offset, length]) => [ids[index], offset, length]);
  const manifest = { format: 'cad-share/2', files: placed };
  const sealed = new Map();
  for (const [index, pack] of packs.entries()) sealed.set(ids[index], await seal(id, pack, `cad-share/2 pack ${ids[index]}`));
  return { id, manifest, packs: ids, sealed, sealedManifest: await seal(id, encode(manifest), 'cad-share/2 manifest') };
}

/**
 * A stand-in for the share service's reads of `share`: what it was asked, by pack id in order, and how many at most
 * at once. With `hold`, a pack is answered only once `release(id)` lets it go.
 */
function serve(share, { hold = false } = {}) {
  const asked = [];
  const released = new Map();
  const waiters = [];
  const signals = new Map();
  let fetching = 0;
  let most = 0;
  const gate = id => {
    let entry = released.get(id);
    if (!entry) { let open; entry = { promise: new Promise(resolve => { open = resolve; }), open }; released.set(id, entry); }
    return entry;
  };
  const service = {
    manifest: async () => body(share.sealedManifest),
    async pack(id, { signal } = {}) {
      asked.push(id);
      signals.set(id, signal);
      for (const waiter of waiters.filter(waiter => asked.length >= waiter.count)) waiter.resolve();
      fetching += 1;
      most = Math.max(most, fetching);
      try {
        if (hold) {
          await new Promise((resolve, reject) => {
            gate(id).promise.then(resolve);
            signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true });
          });
        }
        const sealed = share.sealed.get(id);
        if (!sealed) throw Object.assign(new Error('The share service answered 404 to a pack of the shared model\'s request.'), { status: 404 });
        return body(sealed);
      } finally {
        fetching -= 1;
      }
    },
  };
  return {
    service, asked, signals,
    most: () => most,
    release: id => gate(id).open(),
    /** Once `count` packs have been asked for. */
    asks: count => (asked.length >= count ? Promise.resolve() : new Promise(resolve => waiters.push({ count, resolve }))),
  };
}
/** Every macrotask and microtask before it done: what was started has asked what it will. */
const settled = () => new Promise(resolve => setImmediate(resolve));

// A view bundle of a mesh file to share: its manifest (`view-bundle/1`), its source and other files the page may
// read through the service's resources.
const DOCUMENT = { id: '1024a2f2-2b65-5151-8299-282973f2a9fc', kind: 'stl', name: 'part.stl', version: 'v1' };
function bundle(files, document = DOCUMENT) {
  const listed = Object.fromEntries(Object.entries(files).map(([path, bytes]) => [path,
    { bytes: bytes.length, sha256: sha256(bytes), type: 'application/octet-stream' }]));
  return { 'manifest.json': encode({ format: 'view-bundle/1', document, files: listed }), ...files };
}
const readAll = async (client, paths) => Promise.all(paths.map(async path => new Uint8Array(await client.resources.readBytes(path))));
const refusedAs = (code, pattern) => error => error?.code === code && (!pattern || pattern.test(error.message));

test("a share's key and name are its id's, and its objects are sealed, as the contract's vectors say", async () => {
  assert.equal(hex(await deriveShareBits(VECTORS.id, 'key')), VECTORS.key);
  assert.equal(hex(await deriveShareBits(VECTORS.id, 'name')), VECTORS.name);
  // This file seals as the service does: with a zero IV, the vectors' own bytes.
  const zero = new Uint8Array(12);
  assert.equal(hex(await seal(VECTORS.id, encode(VECTORS.manifest), 'cad-share/2 manifest', zero)), VECTORS.manifestSealed);
  assert.equal(sha256(encode(VECTORS.pack)), VECTORS.packId);
  assert.equal(hex(await seal(VECTORS.id, encode(VECTORS.pack), `cad-share/2 pack ${VECTORS.packId}`, zero)), VECTORS.packSealed);

  // The page opens the vector's manifest, and refuses it for what it holds (no files), not as bytes that do not open.
  const vector = Buffer.from(VECTORS.manifestSealed, 'hex');
  const unasked = async () => { throw new Error('no pack is asked for'); };
  await assert.rejects(openShare(VECTORS.id, { manifest: async () => body(vector), pack: unasked }),
    refusedAs(SHARE_DAMAGED, /lists no manifest\.json/));
  // Under another id's key, sealed for a pack, or a byte changed, it does not open.
  await assert.rejects(openShare(newId(), { manifest: async () => body(vector), pack: unasked }), refusedAs(SHARE_DAMAGED, /manifest does not open/));
  const asPack = await seal(VECTORS.id, encode(VECTORS.manifest), `cad-share/2 pack ${VECTORS.packId}`);
  await assert.rejects(openShare(VECTORS.id, { manifest: async () => body(asPack), pack: unasked }), refusedAs(SHARE_DAMAGED, /manifest does not open/));
  for (const at of [0, 11, 12, vector.length - 1]) {
    const changed = Buffer.from(vector);
    changed[at] ^= 1;
    await assert.rejects(openShare(VECTORS.id, { manifest: async () => body(changed), pack: unasked }),
      refusedAs(SHARE_DAMAGED, /manifest does not open/), `byte ${at}`);
  }
  // The vector's pack opens under its id: what it holds is then read as a file's gzip member, which it is not.
  const naming = { format: 'cad-share/2', files: { 'manifest.json': { sha256: sha256(encode(VECTORS.pack)), bytes: 10, at: [[VECTORS.packId, 0, 10]] } } };
  const manifest = await seal(VECTORS.id, encode(naming), 'cad-share/2 manifest');
  const pack = async id => (id === VECTORS.packId ? body(Buffer.from(VECTORS.packSealed, 'hex')) : unasked());
  await assert.rejects(openShare(VECTORS.id, { manifest: async () => body(manifest), pack }),
    refusedAs(SHARE_DAMAGED, /manifest\.json is no whole gzip member/));
});

test("a share's files are read from the packs that hold them, one split over two, each pack fetched once", async () => {
  const files = { 'source.stl': noise(700, 1), 'parts/a.glb': noise(300, 2), 'meshes/b.stl': noise(900, 3), 'parts/empty.bin': new Uint8Array(0),
    'look.json': encode({ version: 4 }) };
  const share = await makeShare(bundle(files), { packBytes: 512 });
  const split = Object.values(share.manifest.files).filter(entry => new Set(entry.at.map(([id]) => id)).size > 1);
  assert.ok(share.packs.length > 3 && split.length, `${share.packs.length} packs, ${split.length} files split`);
  const { service, asked } = serve(share);
  const client = await openShare(share.id, service);
  assert.deepEqual(client.manifest.document, DOCUMENT);
  assert.equal(client.file, '/part.stl');
  assert.deepEqual(await readAll(client, Object.keys(files)), Object.values(files));
  assert.deepEqual([...asked].sort(), [...share.packs].sort(), 'each pack once');
  // Read again, every file comes from the packs held.
  assert.deepEqual(await readAll(client, Object.keys(files)), Object.values(files));
  assert.equal(asked.length, share.packs.length);
  // A worker is handed its own copy: what it detaches is never the next read's.
  const ticket = await client.resources.workerTicket('source.stl');
  structuredClone(ticket.bytes, { transfer: [ticket.bytes] });
  assert.deepEqual(new Uint8Array(await client.resources.readBytes('source.stl')), files['source.stl']);
  client.dispose();
});

test('every pack is fetched ahead, six at a time and the manifest\'s first, and a read takes its pack ahead of the rest', async () => {
  const files = Object.fromEntries(Array.from({ length: 9 }, (_, index) => [`parts/${index}.glb`, noise(200 + index, 10 + index)]));
  // The bundle's manifest packed last, in a pack of its own as every file is here.
  const { 'manifest.json': listing, ...rest } = bundle(files);
  const share = await makeShare({ ...rest, 'manifest.json': listing }, { each: true });
  const packOf = path => share.manifest.files[path].at[0][0];
  assert.equal(share.packs.length, 10);
  const { service, asked, release, asks, most } = serve(share, { hold: true });
  let opened = null;
  const opening = openShare(share.id, service).then(client => { opened = client; return client; });
  await asks(SHARE_PREFETCH);
  await settled();
  // As soon as the manifest is read, six packs at once: the one holding the bundle's manifest first, then in order.
  assert.deepEqual(asked, [packOf('manifest.json'), ...share.packs.slice(0, SHARE_PREFETCH - 1)]);
  assert.equal(opened, null);
  release(packOf('manifest.json'));
  const client = await opening;
  await asks(SHARE_PREFETCH + 1);
  await settled();
  assert.deepEqual(asked, [packOf('manifest.json'), ...share.packs.slice(0, SHARE_PREFETCH)]);
  // A read of a file whose pack waits in line: its pack goes next, and the read waits for it alone.
  const last = Object.keys(files).at(-1);
  let read = null;
  const reading = client.resources.readBytes(last).then(bytes => { read = new Uint8Array(bytes); });
  await settled();
  assert.equal(asked.length, SHARE_PREFETCH + 1, 'no seventh pack at once');
  release(share.packs[0]);
  await asks(SHARE_PREFETCH + 2);
  assert.equal(asked.at(-1), packOf(last));
  await settled();
  assert.equal(read, null);
  release(packOf(last));
  await reading;
  assert.deepEqual(read, files[last]);
  // The rest come in their turn, each once, never more than six at a time.
  for (const id of share.packs) release(id);
  assert.deepEqual(await readAll(client, Object.keys(files)), Object.values(files));
  assert.deepEqual([...asked].sort(), [...share.packs].sort());
  assert.ok(most() <= SHARE_PREFETCH, `${most()} at once`);
  client.dispose();
});

test('a share closed, or never opened, stops what it fetches ahead', async () => {
  const files = Object.fromEntries(Array.from({ length: 8 }, (_, index) => [`parts/${index}.glb`, noise(100, 30 + index)]));
  const share = await makeShare(bundle(files), { each: true });
  const stopped = serve(share, { hold: true });
  const controller = new AbortController();
  const opening = openShare(share.id, stopped.service, { signal: controller.signal });
  await stopped.asks(SHARE_PREFETCH);
  controller.abort();
  await assert.rejects(opening, error => error.name === 'AbortError');
  assert.ok(share.packs.slice(0, SHARE_PREFETCH).every(id => stopped.signals.get(id)?.aborted));
  for (const id of share.packs) stopped.release(id);
  await settled();
  assert.equal(stopped.asked.length, SHARE_PREFETCH, 'nothing asked once it stopped');

  const closed = serve(share, { hold: true });
  const opened = openShare(share.id, closed.service);
  await closed.asks(SHARE_PREFETCH);
  closed.release(share.packs[0]);
  const client = await opened;
  const waiting = client.resources.readBytes(Object.keys(files).at(-1));
  client.dispose();
  await assert.rejects(waiting, error => error.name === 'AbortError');
  assert.ok(closed.asked.slice(1).every(id => closed.signals.get(id)?.aborted));
});

test('a manifest that does not open or is not one, and a file not as it says, are a damaged link', async () => {
  const files = { 'source.stl': noise(400, 4), 'parts/a.glb': noise(300, 5) };
  const share = await makeShare(bundle(files), { packBytes: 256 });
  const sealedAs = async manifest => body(await seal(share.id, encode(manifest), 'cad-share/2 manifest'));
  const opening = (manifest, pack = serve(share).service.pack) => openShare(share.id, { manifest: async () => manifest, pack });
  // Not JSON, and not a share's manifest, each saying what.
  await assert.rejects(opening(await sealedAs('{"format":')), refusedAs(SHARE_DAMAGED, /not JSON/));
  const entry = share.manifest.files['source.stl'];
  const withFile = (path, value) => ({ format: 'cad-share/2', files: { ...share.manifest.files, [path]: value } });
  const shapes = {
    'an array': [[], /not an object/],
    'another format': [{ ...share.manifest, format: 'cad-share/1' }, /"cad-share\/1", not cad-share\/2/],
    'no files': [{ format: 'cad-share/2' }, /lists no files/],
    'no bundle manifest': [{ format: 'cad-share/2', files: { 'source.stl': entry } }, /lists no manifest\.json/],
    'a path with ..': [withFile('parts/../x', entry), /no path inside a bundle/],
    'an absolute path': [withFile('/etc/passwd', entry), /no path inside a bundle/],
    'an empty segment': [withFile('parts//x', entry), /no path inside a bundle/],
    'a path too long': [withFile(`parts/${'x'.repeat(1020)}`, entry), /no path inside a bundle/],
    'no digest': [withFile('x', { ...entry, sha256: 'ABC' }), /no SHA-256, size and ranges/],
    'a size below zero': [withFile('x', { ...entry, bytes: -1 }), /no SHA-256, size and ranges/],
    'no ranges': [withFile('x', { ...entry, at: [] }), /no SHA-256, size and ranges/],
    'a range of no pack': [withFile('x', { ...entry, at: [['pack', 0, 1]] }), /no SHA-256, size and ranges/],
    'a range at no whole offset': [withFile('x', { ...entry, at: [[entry.at[0][0], 0.5, 1]] }), /no SHA-256, size and ranges/],
  };
  for (const [what, [manifest, said]] of Object.entries(shapes)) await assert.rejects(opening(await sealedAs(manifest)), refusedAs(SHARE_DAMAGED, said), what);

  // A file whose bytes are not the manifest's: another digest, another size, a range past its pack, a pack that does
  // not open, ranges that are no gzip member. The bundle's manifest refuses the share; any other file, its read.
  const pack = share.manifest.files['manifest.json'].at[0][0];
  const lying = {
    'another digest': [listed => ({ ...listed, sha256: sha256(encode('other')) }), /SHA-256 differs/],
    'more bytes than it says': [listed => ({ ...listed, bytes: listed.bytes - 1 }), /holds more than the \d+ bytes/],
    'fewer bytes than it says': [listed => ({ ...listed, bytes: listed.bytes + 1 }), /is \d+ bytes; the share's manifest says \d+/],
    'a range past its pack': [listed => ({ ...listed, at: [[pack, 1 << 20, 10]] }), /past the end of the pack/],
    'no gzip member': [listed => ({ ...listed, at: [[pack, 1, 40]] }), /no whole gzip member/],
  };
  for (const [what, [lie, said]] of Object.entries(lying)) {
    await assert.rejects(opening(await sealedAs(withFile('manifest.json', lie(share.manifest.files['manifest.json'])))),
      refusedAs(SHARE_DAMAGED, said), `manifest.json: ${what}`);
    const client = await opening(await sealedAs(withFile('source.stl', lie(entry))));
    await assert.rejects(client.resources.readBytes('source.stl'), refusedAs(SHARE_DAMAGED, said), what);
    client.dispose();
  }
  const resealed = new Map(share.sealed);
  resealed.set(pack, await seal(share.id, new Uint8Array(64), `cad-share/2 pack ${share.packs.at(-1)}`));
  const elsewhere = { ...share, sealed: resealed };
  await assert.rejects(opening(body(share.sealedManifest), serve(elsewhere).service.pack), refusedAs(SHARE_DAMAGED, new RegExp(`pack ${pack} does not open`)));
  // An address that is no share's opens nothing.
  await assert.rejects(openShare('not-a-share', serve(share).service), refusedAs(SHARE_DAMAGED, /names no share/));
});

test("the service's answer is said as it is, a pack it did not give is asked for again, and a bundle this viewer does not open says so", async () => {
  const files = { 'source.stl': noise(300, 6), 'parts/a.glb': noise(300, 7) };
  const share = await makeShare(bundle(files), { each: true });
  // The host's read of the manifest says why it has none (a share the service has none of, a refusal, no network).
  const gone = Object.assign(new Error('This shared model has expired or was deleted.'), { code: 'share-gone', status: 404 });
  const asked = [];
  await assert.rejects(openShare(share.id, { manifest: async () => { throw gone; }, pack: async id => { asked.push(id); } }), error => error === gone);
  assert.deepEqual(asked, []);

  // A pack it did not give, at the start or later: the share is not damaged, and the next read asks again.
  const missing = new Map(share.sealed);
  missing.delete(share.manifest.files['manifest.json'].at[0][0]);
  await assert.rejects(openShare(share.id, serve({ ...share, sealed: missing }).service),
    refusedAs(SHARE_UNAVAILABLE, /manifest\.json could not be fetched: .*404/));
  const later = new Map(share.sealed);
  const glb = share.manifest.files['parts/a.glb'].at[0][0];
  later.delete(glb);
  const flaky = { ...share, sealed: later };
  const { service, asked: fetched } = serve(flaky);
  const client = await openShare(share.id, service);
  const failure = await client.resources.readBytes('parts/a.glb').catch(error => error);
  assert.ok(refusedAs(SHARE_UNAVAILABLE)(failure), String(failure));
  assert.equal(failure.cause.status, 404);
  later.set(glb, share.sealed.get(glb));
  assert.deepEqual(new Uint8Array(await client.resources.readBytes('parts/a.glb')), files['parts/a.glb']);
  assert.ok(fetched.filter(id => id === glb).length >= 2, 'asked again');
  // A path the share does not hold is a bundle's missing file.
  await assert.rejects(client.resources.readBytes('parts/unlisted.glb'), error => error.status === 404);
  client.dispose();

  // A bundle in a layout this viewer does not read, or no bundle at all, opens nothing, saying why.
  const later9 = await makeShare({ 'manifest.json': encode({ format: 'view-bundle/9', document: DOCUMENT, files: {} }) });
  await assert.rejects(openShare(later9.id, serve(later9).service), refusedAs(SHARE_UNSUPPORTED, /view-bundle\/9/));
  const notJson = await makeShare({ 'manifest.json': encode('{') });
  await assert.rejects(openShare(notJson.id, serve(notJson).service), refusedAs(SHARE_UNSUPPORTED, /not JSON/));
});

test("a share's address is its id alone as the path; a delete secret after the # makes it the delete page", () => {
  const id = 'AbCdEfGhIjKlMnOpQrSt_-';
  const secret = Buffer.from(new Uint8Array(32).fill(7)).toString('base64url');
  assert.deepEqual(readShareAddress(`https://cad.example/${id}`), { id });
  assert.deepEqual(readShareAddress(`http://127.0.0.1:8080/${id}#delete=${secret}`), { id, deleteSecret: secret });
  assert.deepEqual(readShareAddress(`https://cad.example/${id}#delete=`), { id, deleteSecret: '' });
  // Whatever else follows the id is passed over: a key a link once carried, a fragment cut short.
  for (const href of [`https://cad.example/${id}#key=${secret}`, `https://cad.example/${id}#`, `https://cad.example/${id}#k=1`,
    `https://cad.example/${id}?from=mail`]) assert.deepEqual(readShareAddress(href), { id }, href);
  for (const href of [
    `https://cad.example/${id}/`, `https://cad.example/x/${id}`, `https://cad.example/${id}x`, `https://cad.example/${id.slice(1)}`,
    `https://cad.example/${id.replace('_', '.')}`, 'https://cad.example/', 'https://cad.example/1024a2f2-2b65-5151-8299-282973f2a9fc',
    `https://cad.example/?bundle=a.view/#delete=${secret}`,
  ]) assert.equal(readShareAddress(href), null, href);
  assert.equal(isShareSecret(secret), true);
  for (const value of ['', secret.slice(1), `${secret}=`, `${secret.slice(0, 42)}/`, null]) assert.equal(isShareSecret(value), false, String(value));
});
