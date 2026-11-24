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
 * A share of a view bundle's files (`view`, path to bytes, in reading order) and the files that made it (`files`,
 * after them) as the command packs one and the service seals it: each file's gzip member back to back in packs
 * closed at `packBytes` (a member that does not fit the room left goes on into the next pack), or in a pack of its
 * own each (`each`), a file whose SHA-256 is one already placed given that one's ranges; each pack named by its
 * SHA-256; the manifest naming the document (a file document's, unless `entry` and `made` say a model's) and every
 * file's ranges.
 */
async function makeShare(view, { files = {}, name = 'part.stl', entry = null, made = null, packBytes = 4 << 20, each = false, id = newId() } = {}) {
  const packs = [];
  let open = [];
  let used = 0;
  const close = () => { if (used) packs.push(Buffer.concat(open)); open = []; used = 0; };
  const members = new Map();
  const place = map => Object.fromEntries(Object.entries(map).map(([path, bytes]) => {
    if (members.has(sha256(bytes))) return [path, { sha256: sha256(bytes), bytes: bytes.length, at: members.get(sha256(bytes)) }];
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
    if (each) close();
    members.set(sha256(bytes), at);
    return [path, { sha256: sha256(bytes), bytes: bytes.length, at }];
  }));
  const placed = { view: place(view), files: place(files) };
  close();
  const ids = packs.map(sha256);
  const named = new Map([...members.values()].map(at => [at, at.map(([index, offset, length]) => [ids[index], offset, length])]));
  for (const file of [...Object.values(placed.view), ...Object.values(placed.files)]) file.at = named.get(file.at);
  const manifest = { format: 'cad-share/2', name, entry, made, ...placed };
  const sealed = new Map();
  for (const [index, pack] of packs.entries()) sealed.set(ids[index], await seal(id, pack, `cad-share/2 pack ${ids[index]}`));
  return { id, manifest, packs: ids, sealed, sealedManifest: await seal(id, encode(manifest), 'cad-share/2 manifest') };
}
/** The packs a manifest's map of files (`view`, `files`) names. */
const packsOf = map => new Set(Object.values(map).flatMap(file => file.at.map(([pack]) => pack)));

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

  // The page opens the vector's manifest, and refuses it for what it holds (the earlier shape: files, and no view),
  // not as bytes that do not open.
  const vector = Buffer.from(VECTORS.manifestSealed, 'hex');
  const unasked = async () => { throw new Error('no pack is asked for'); };
  await assert.rejects(openShare(VECTORS.id, { manifest: async () => body(vector), pack: unasked }),
    refusedAs(SHARE_DAMAGED, /has no view/));
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
  const naming = { format: 'cad-share/2', name: 'part.stl', entry: null, made: null, files: {},
    view: { 'manifest.json': { sha256: sha256(encode(VECTORS.pack)), bytes: 10, at: [[VECTORS.packId, 0, 10]] } } };
  const manifest = await seal(VECTORS.id, encode(naming), 'cad-share/2 manifest');
  const pack = async id => (id === VECTORS.packId ? body(Buffer.from(VECTORS.packSealed, 'hex')) : unasked());
  await assert.rejects(openShare(VECTORS.id, { manifest: async () => body(manifest), pack }),
    refusedAs(SHARE_DAMAGED, /manifest\.json is no whole gzip member/));
});

test("a share's files are read from the packs that hold them, one split over two, each pack fetched once", async () => {
  const files = { 'source.stl': noise(700, 1), 'parts/a.glb': noise(300, 2), 'meshes/b.stl': noise(900, 3), 'parts/empty.bin': new Uint8Array(0),
    'look.json': encode({ version: 4 }) };
  const share = await makeShare(bundle(files), { packBytes: 512 });
  const split = Object.values(share.manifest.view).filter(entry => new Set(entry.at.map(([id]) => id)).size > 1);
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
  // A file document's share told as it is: its name, no script, nothing of what built it, no files that made it.
  assert.deepEqual(client.share, { name: 'part.stl', entry: null, made: null, files: [] });
  client.dispose();
});

test("a model's share holds the files that made it beside its view: the page fetches no pack only they name, and is told what they are", async () => {
  // The view's files, then the files that made it in the same packs after them, as the command packs a model: the
  // last pack of the view's goes on with the first of the files, and the rest of the files have packs of their own.
  // The bundle's own listing names one of those files too, as though the view held it; the share's view does not.
  const { 'lib/head.py': head, ...view } = bundle({ 'source.stl': noise(700, 50), 'parts/a.glb': noise(300, 51), 'lib/head.py': noise(900, 52) });
  // A path may be both the view's and the files' (separate maps): the same bytes, and so the same ranges.
  const files = { 'part.py': noise(600, 53), 'lib/head.py': head, 'source.stl': view['source.stl'] };
  const made = { cad: '0.11.17', build123d: '0.13.0', OCP: '8.0.1.1.0', bd_materials: '0.2.6', threejs_materials: '1.2.5',
    python: '3.13.18', system: 'Linux', arch: 'x86_64' };
  const share = await makeShare(view, { files, name: 'part', entry: 'part.py', made, packBytes: 512 });
  assert.deepEqual(share.manifest.files['source.stl'].at, share.manifest.view['source.stl'].at);
  const viewed = packsOf(share.manifest.view);
  const theirs = [...packsOf(share.manifest.files)].filter(pack => !viewed.has(pack));
  assert.ok(theirs.length >= 2 && [...packsOf(share.manifest.files)].some(pack => viewed.has(pack)), 'a pack of both, and packs of the files alone');
  const { service, asked } = serve(share);
  const client = await openShare(share.id, service);
  assert.deepEqual(await readAll(client, ['source.stl', 'parts/a.glb']), [view['source.stl'], view['parts/a.glb']]);
  // Asked for one of the files alone, the share has no such file of its view, and fetches nothing for it.
  await assert.rejects(client.resources.readBytes('lib/head.py'), error => error.status === 404 && /holds no lib\/head\.py/.test(error.message));
  await settled();
  assert.deepEqual([...asked].sort(), [...viewed].sort(), 'every pack of the view once, and none of the files alone');
  // What the share holds beside its view, as its manifest says it.
  assert.deepEqual(client.share, { name: 'part', entry: 'part.py', made, files: ['part.py', 'lib/head.py', 'source.stl'] });
  assert.ok([client.share, client.share.made, client.share.files].every(Object.isFrozen));
  client.dispose();
});

test('every pack is fetched ahead, six at a time and the manifest\'s first, and a read takes its pack ahead of the rest', async () => {
  const files = Object.fromEntries(Array.from({ length: 9 }, (_, index) => [`parts/${index}.glb`, noise(200 + index, 10 + index)]));
  // The bundle's manifest packed last, in a pack of its own as every file is here.
  const { 'manifest.json': listing, ...rest } = bundle(files);
  const share = await makeShare({ ...rest, 'manifest.json': listing }, { each: true });
  const packOf = path => share.manifest.view[path].at[0][0];
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
  const entry = share.manifest.view['source.stl'];
  const withFile = (path, value) => ({ ...share.manifest, view: { ...share.manifest.view, [path]: value } });
  const withSource = (path, value) => ({ ...share.manifest, files: { ...share.manifest.files, [path]: value } });
  const without = member => Object.fromEntries(Object.entries(share.manifest).filter(([name]) => name !== member));
  const shapes = {
    'an array': [[], /not an object/],
    'another format': [{ ...share.manifest, format: 'cad-share/1' }, /"cad-share\/1", not cad-share\/2/],
    // The earlier shape: every file of the bundle as `files`, and nothing of the document.
    'the earlier shape': [{ format: 'cad-share/2', files: share.manifest.view }, /has no view/],
    'another member': [{ ...share.manifest, key: 'k' }, /holds "key", which a share's manifest does not/],
    'no view': [{ ...share.manifest, view: [] }, /has no view/],
    'no files that made it': [{ ...share.manifest, files: null }, /lists no files that made it/],
    'no name': [without('name'), /names its document nothing, not 1 to 200 characters/],
    'an empty name': [{ ...share.manifest, name: '' }, /names its document "", not 1 to 200 characters/],
    'a name too long': [{ ...share.manifest, name: 'x'.repeat(201) }, /not 1 to 200 characters/],
    'a name with a control character': [{ ...share.manifest, name: 'part\n.stl' }, /not 1 to 200 characters of text/],
    'a name of no text': [{ ...share.manifest, name: 'part\ud800' }, /not 1 to 200 characters of text/],
    'no entry': [without('entry'), /names nothing as its script/],
    'an entry none of its files': [{ ...share.manifest, entry: 'gone.py' }, /names "gone\.py" as its script, which is none of the files/],
    // A model's script is among the files that made it, never only among its view's.
    'an entry of the view alone': [{ ...share.manifest, entry: 'manifest.json' }, /as its script, which is none of the files/],
    'no made': [without('made'), /says what built it as nothing/],
    'a made that is a list': [{ ...share.manifest, made: ['cad'] }, /says what built it as \["cad"\]/],
    'a made value of no text': [{ ...share.manifest, made: { cad: 11 } }, /says what built it/],
    'a made value too long': [{ ...share.manifest, made: { cad: 'x'.repeat(101) } }, /at most 32 names and values of 100 characters/],
    'a made name too long': [{ ...share.manifest, made: { ['x'.repeat(101)]: '1' } }, /at most 32 names and values/],
    'a made of 33 members': [{ ...share.manifest, made: Object.fromEntries(Array.from({ length: 33 }, (_, index) => [`lib${index}`, '1'])) },
      /at most 32 names and values/],
    // 200,000 files at most, counted over both maps (each refused for its count before its shape is read).
    'too many files over both maps': [{ ...share.manifest,
      view: { ...share.manifest.view, ...Object.fromEntries(Array.from({ length: 100_000 }, (_, index) => [`v${index}`, 0])) },
      files: Object.fromEntries(Array.from({ length: 100_000 }, (_, index) => [`f${index}`, 0])) }, /lists 200003 files, more than 200000/],
    'no bundle manifest': [{ ...share.manifest, view: { 'source.stl': entry } }, /lists no manifest\.json in its view/],
    'a path with ..': [withFile('parts/../x', entry), /in its view, which is no path inside a bundle/],
    'an absolute path': [withFile('/etc/passwd', entry), /no path inside a bundle/],
    'an empty segment': [withFile('parts//x', entry), /no path inside a bundle/],
    'a path too long': [withFile(`parts/${'x'.repeat(1020)}`, entry), /no path inside a bundle/],
    'no digest': [withFile('x', { ...entry, sha256: 'ABC' }), /gives "x" in its view no SHA-256, size and ranges/],
    'a size below zero': [withFile('x', { ...entry, bytes: -1 }), /no SHA-256, size and ranges/],
    'no ranges': [withFile('x', { ...entry, at: [] }), /no SHA-256, size and ranges/],
    'a range of no pack': [withFile('x', { ...entry, at: [['pack', 0, 1]] }), /no SHA-256, size and ranges/],
    'a range at no whole offset': [withFile('x', { ...entry, at: [[entry.at[0][0], 0.5, 1]] }), /no SHA-256, size and ranges/],
    // The files that made it keep the same paths and entries as the view's, though the page reads none of them.
    'a file that made it outside its folder': [withSource('../part.py', entry), /in the files that made it, which is no path inside a folder/],
    'an absolute file that made it': [withSource('C:/part.py', entry), /in the files that made it, which is no path inside a folder/],
    'a file that made it with no ranges': [withSource('lib/head.py', { ...entry, at: [] }), /gives "lib\/head\.py" in the files that made it no SHA-256/],
  };
  for (const [what, [manifest, said]] of Object.entries(shapes)) await assert.rejects(opening(await sealedAs(manifest)), refusedAs(SHARE_DAMAGED, said), what);
  // At its limits it is a share: a name of 200 characters (each one code point, however many UTF-16 units it takes),
  // and what built it in 32 names and values of 100 characters each.
  const made = Object.fromEntries(Array.from({ length: 32 }, (_, index) => [String(index).padStart(100, 'x'), 'é'.repeat(100)]));
  const limits = { ...share.manifest, name: '🧩'.repeat(200), entry: 'part.py', made, files: { 'part.py': entry } };
  const opened = await opening(await sealedAs(limits));
  assert.deepEqual(opened.share, { name: limits.name, entry: 'part.py', made, files: ['part.py'] });
  opened.dispose();

  // A file whose bytes are not the manifest's: another digest, another size, a range past its pack, a pack that does
  // not open, ranges that are no gzip member. The bundle's manifest refuses the share; any other file, its read.
  const pack = share.manifest.view['manifest.json'].at[0][0];
  const lying = {
    'another digest': [listed => ({ ...listed, sha256: sha256(encode('other')) }), /SHA-256 differs/],
    'more bytes than it says': [listed => ({ ...listed, bytes: listed.bytes - 1 }), /holds more than the \d+ bytes/],
    'fewer bytes than it says': [listed => ({ ...listed, bytes: listed.bytes + 1 }), /is \d+ bytes; the share's manifest says \d+/],
    'a range past its pack': [listed => ({ ...listed, at: [[pack, 1 << 20, 10]] }), /past the end of the pack/],
    'no gzip member': [listed => ({ ...listed, at: [[pack, 1, 40]] }), /no whole gzip member/],
  };
  for (const [what, [lie, said]] of Object.entries(lying)) {
    await assert.rejects(opening(await sealedAs(withFile('manifest.json', lie(share.manifest.view['manifest.json'])))),
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
  missing.delete(share.manifest.view['manifest.json'].at[0][0]);
  await assert.rejects(openShare(share.id, serve({ ...share, sealed: missing }).service),
    refusedAs(SHARE_UNAVAILABLE, /manifest\.json could not be fetched: .*404/));
  const later = new Map(share.sealed);
  const glb = share.manifest.view['parts/a.glb'].at[0][0];
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
