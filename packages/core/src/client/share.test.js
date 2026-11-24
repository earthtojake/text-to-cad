import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
import test from 'node:test';
import { gzipSync } from 'node:zlib';
import { isShareSecret, openShareArchive, readShareAddress, readShareArchive, readShareKey,
  SHARE_UNREADABLE, SHARE_UNSUPPORTED } from './share.js';

// A share made here as its maker makes one: a view bundle's files as a POSIX ustar archive (sorted, each a
// regular file, mtime 0, mode 0644), gzipped, encrypted with AES-256-GCM under a fresh key and IV, stored as
// `IV || ciphertext-and-tag`.
const encode = value => new TextEncoder().encode(typeof value === 'string' ? value : JSON.stringify(value));
const base64url = bytes => Buffer.from(bytes).toString('base64url');

/** One ustar header: `name` split at a `/` into the prefix field where it is longer than the name field. */
function header(path, size, { type = '0', link = '' } = {}) {
  const block = new Uint8Array(512);
  const put = (text, at, length) => { const bytes = encode(text); assert.ok(bytes.length <= length, text); block.set(bytes, at); };
  let name = path;
  let prefix = '';
  if (encode(path).length > 100) {
    const cut = path.lastIndexOf('/', 155);
    prefix = path.slice(0, cut);
    name = path.slice(cut + 1);
  }
  put(name, 0, 100);
  put('0000644\0', 100, 8);
  put('0000000\0', 108, 8);
  put('0000000\0', 116, 8);
  put(`${size.toString(8).padStart(11, '0')}\0`, 124, 12);
  put('00000000000\0', 136, 12);
  put('        ', 148, 8);
  put(type, 156, 1);
  put(link, 157, 100);
  put('ustar\u000000', 257, 8);
  put(prefix, 345, 155);
  const sum = block.reduce((total, byte) => total + byte, 0);
  put(`${sum.toString(8).padStart(6, '0')}\0 `, 148, 8);
  return block;
}
/** An archive of `entries`: [path, bytes, options] in order, then the two zero blocks. */
function ustar(entries) {
  const parts = [];
  for (const [path, bytes, options] of entries) {
    parts.push(header(path, bytes.length, options), bytes, new Uint8Array((512 - (bytes.length % 512)) % 512));
  }
  parts.push(new Uint8Array(1024));
  return Buffer.concat(parts);
}
async function seal(archive, raw = webcrypto.getRandomValues(new Uint8Array(32))) {
  const key = await webcrypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['encrypt']);
  const iv = webcrypto.getRandomValues(new Uint8Array(12));
  const sealed = new Uint8Array(await webcrypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, archive));
  return { stored: Buffer.concat([iv, sealed]), key: base64url(raw) };
}
const share = (entries) => seal(gzipSync(ustar(entries)));

// A small view bundle of a mesh file: its manifest and its one source file.
const SOURCE = encode('solid t\nendsolid t\n');
const DOCUMENT = { id: '1024a2f2-2b65-5151-8299-282973f2a9fc', kind: 'stl', name: 'part.stl', version: 'v1' };
const MANIFEST = encode({ format: 'view-bundle/1', document: DOCUMENT, files: { 'source.stl': { bytes: SOURCE.length } } });
const BUNDLE = [['manifest.json', MANIFEST], ['source.stl', SOURCE]];
const refusedAs = code => error => error?.code === code;

test('a share opens to its bundle: the files it holds, and the view bundle they are', async () => {
  const long = `parts/${'k'.repeat(90)}/${'t'.repeat(60)}.xbm`;
  const { stored, key } = await share([...BUNDLE, [long, encode('XBM2')]]);
  const files = await readShareArchive(stored.buffer.slice(stored.byteOffset, stored.byteOffset + stored.byteLength), key);
  assert.deepEqual([...files.keys()], ['manifest.json', 'source.stl', long]);
  assert.deepEqual(files.get('source.stl'), SOURCE);
  // A path longer than a header's name is read through its prefix field.
  assert.equal(new TextDecoder().decode(files.get(long)), 'XBM2');
  const client = await openShareArchive(stored, key);
  assert.deepEqual(client.manifest.document, DOCUMENT);
  assert.equal(client.file, '/part.stl');
  client.dispose();
});

test('a wrong key, a missing or malformed one, and damaged bytes are one refusal: the link is incomplete or damaged', async () => {
  const { stored, key } = await share(BUNDLE);
  const other = base64url(webcrypto.getRandomValues(new Uint8Array(32)));
  await assert.rejects(readShareArchive(stored, other), refusedAs(SHARE_UNREADABLE));
  for (const malformed of ['', key.slice(0, 20), `${key}A`, `${key.slice(0, 42)}+`]) {
    await assert.rejects(readShareArchive(stored, malformed), refusedAs(SHARE_UNREADABLE));
  }
  for (const at of [0, 11, 12, stored.length - 1]) {
    const flipped = Buffer.from(stored);
    flipped[at] ^= 0x01;
    await assert.rejects(readShareArchive(flipped, key), refusedAs(SHARE_UNREADABLE), `a byte flipped at ${at}`);
  }
  await assert.rejects(readShareArchive(stored.subarray(0, 20), key), refusedAs(SHARE_UNREADABLE));
  // The key is never said back.
  await assert.rejects(readShareArchive(stored, other), error => !error.message.includes(other) && !error.message.includes(key));
});

test('an archive with an entry it does not read is refused whole, as a format this reader does not read', async () => {
  const refusals = {
    'a path with ..': [...BUNDLE, ['parts/../../escape', encode('x')]],
    'an absolute path': [...BUNDLE, ['/etc/passwd', encode('x')]],
    'a path twice': [...BUNDLE, ['source.stl', SOURCE]],
    'a symbolic link': [...BUNDLE, ['parts/link', new Uint8Array(0), { type: '2', link: '/etc/passwd' }]],
    'a hard link': [...BUNDLE, ['parts/link', new Uint8Array(0), { type: '1', link: 'source.stl' }]],
    'a folder': [['parts/', new Uint8Array(0), { type: '5' }], ...BUNDLE],
    'an extended header': [['pax', encode('30 path=x\n'), { type: 'x' }], ...BUNDLE],
  };
  for (const [what, entries] of Object.entries(refusals)) {
    const { stored, key } = await share(entries);
    await assert.rejects(readShareArchive(stored, key), refusedAs(SHARE_UNSUPPORTED), what);
  }
  // Decrypted bytes that are not gzip, or gzip of something that is no ustar archive.
  for (const archive of [ustar(BUNDLE), gzipSync(encode('no archive here, but long enough to fill a header?'.repeat(12)))]) {
    const { stored, key } = await seal(archive);
    await assert.rejects(readShareArchive(stored, key), refusedAs(SHARE_UNSUPPORTED));
  }
  // An archive cut short, and one past the size it may be read to.
  const whole = ustar(BUNDLE);
  const cut = await seal(gzipSync(whole.subarray(0, 700)));
  await assert.rejects(readShareArchive(cut.stored, cut.key), refusedAs(SHARE_UNSUPPORTED));
  const { stored, key } = await share(BUNDLE);
  await assert.rejects(readShareArchive(stored, key, { maxBytes: 1024 }), refusedAs(SHARE_UNSUPPORTED));
  // Files that are no view bundle (no manifest, another format) do not open as one.
  const bare = await share([['source.stl', SOURCE]]);
  await assert.rejects(openShareArchive(bare.stored, bare.key), refusedAs(SHARE_UNSUPPORTED));
  const later = await share([['manifest.json', encode({ format: 'view-bundle/9', document: DOCUMENT, files: {} })]]);
  await assert.rejects(openShareArchive(later.stored, later.key), error => error.code === SHARE_UNSUPPORTED && /view-bundle\/9/.test(error.message));
});

test("a share's address is its id alone as the path, and its key or delete secret after the #", () => {
  const id = 'AbCdEfGhIjKlMnOpQrSt_-';
  const key = base64url(new Uint8Array(32).fill(7));
  assert.deepEqual(readShareAddress(`https://cad.example/${id}#key=${key}`), { id, key });
  assert.deepEqual(readShareAddress(`http://127.0.0.1:8080/${id}#delete=${key}`), { id, deleteSecret: key });
  // A link cut short is still a share's: it says so when it is opened.
  assert.deepEqual(readShareAddress(`https://cad.example/${id}#key=`), { id, key: '' });
  for (const href of [
    `https://cad.example/${id}`, `https://cad.example/${id}#`, `https://cad.example/${id}#k=${key}`,
    `https://cad.example/${id}/#key=${key}`, `https://cad.example/x/${id}#key=${key}`, `https://cad.example/${id}x#key=${key}`,
    `https://cad.example/${id.slice(1)}#key=${key}`, `https://cad.example/${id.replace('_', '.')}#key=${key}`,
    `https://cad.example/#key=${key}`, 'https://cad.example/1024a2f2-2b65-5151-8299-282973f2a9fc',
    `https://cad.example/?bundle=a.view/#key=${key}`,
  ]) assert.equal(readShareAddress(href), null, href);
  assert.equal(readShareKey(key).length, 32);
  assert.throws(() => readShareKey(key.slice(1)), refusedAs(SHARE_UNREADABLE));
  assert.equal(isShareSecret(key), true);
  for (const text of ['', key.slice(1), `${key}=`, `${key.slice(0, 42)}/`, null]) assert.equal(isShareSecret(text), false, String(text));
});
