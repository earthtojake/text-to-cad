// A shared view bundle: one document's view bundle (`bundle.js`) packed into one archive, encrypted, and
// kept by a share service for a page to open by a link. The link names the share and holds its key in the
// part of the address after `#`, which a browser never sends to a server:
//
//   https://<service>/<id>#key=<key>        the view: the page fetches `/v1/shares/<id>` and opens it
//   https://<service>/<id>#delete=<secret>  the page that deletes the share
//
// `<id>` is 16 random bytes, `<key>` and `<secret>` 32, each base64url with no padding (22 and 43
// characters). The service keeps `IV || ciphertext-and-tag`: the archive encrypted with AES-256-GCM under
// the key and a 12-byte IV. The archive (`cad-share/1`) is the bundle's folder as a gzip-compressed POSIX
// ustar archive: every regular file by its path relative to the bundle's root, `/` separated, and nothing
// else (no folder, link or other entry; no absolute path, no `..`, no path twice).
//
// Opening one here is decrypting it, gunzipping it (`DecompressionStream`) and reading its entries into the
// files a page holds (`viewBundleMemorySource`), then `openViewBundle`. Two failures are told apart, by
// `code`: SHARE_UNREADABLE, a key that is missing, malformed or not the one the archive was encrypted
// under, or bytes damaged on the way (AES-GCM cannot tell these apart, and neither does this); and
// SHARE_UNSUPPORTED, bytes that decrypted but are no archive this reader reads (another format, an entry
// it refuses, no view bundle in it). The key is never part of an error's message.

import { openViewBundle, viewBundleMemorySource } from './bundle.js';

/** The archive's one format: the bundle's folder as a gzip-compressed POSIX ustar archive. */
export const SHARE_ARCHIVE_FORMAT = 'cad-share/1';
/** A share's id: 16 random bytes, base64url without padding. */
export const SHARE_ID_PATTERN = /^[A-Za-z0-9_-]{22}$/;
/** A key or a secret: 32 random bytes, base64url without padding. */
const SECRET_PATTERN = /^[A-Za-z0-9_-]{43}$/;
/** No key, a wrong key, or damaged bytes: the link is incomplete or damaged. */
export const SHARE_UNREADABLE = 'share-unreadable';
/** Bytes that decrypted but hold no archive this reader reads. */
export const SHARE_UNSUPPORTED = 'share-unsupported';
/** The most bytes a share's archive is read to, once decompressed: past it, it is refused, not read on. */
export const SHARE_MAX_BYTES = 1 << 30;

const IV_BYTES = 12;
const TAG_BYTES = 16;
const BLOCK = 512;
const names = new TextDecoder('utf-8', { fatal: true });

const unreadable = (cause) => Object.assign(new Error('This link is incomplete or damaged: its key does not open this shared model.'),
  { code: SHARE_UNREADABLE, ...(cause ? { cause } : {}) });
const unsupported = (detail, cause) => Object.assign(new Error(`This shared model is no ${SHARE_ARCHIVE_FORMAT} archive this viewer reads: ${detail}`),
  { code: SHARE_UNSUPPORTED, ...(cause ? { cause } : {}) });
const abortError = () => new DOMException('The operation was aborted.', 'AbortError');
function checkSignal(signal) { if (signal?.aborted) throw abortError(); }

/** Base64url without padding as bytes, or null where it is none. */
function base64url(text) {
  if (typeof text !== 'string' || !/^[A-Za-z0-9_-]*$/.test(text) || text.length % 4 === 1) return null;
  const binary = atob(text.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat((4 - (text.length % 4)) % 4));
  return Uint8Array.from(binary, char => char.charCodeAt(0));
}

/**
 * What a page's address says of a share, or null where it names none: its path exactly one share id, and
 * its fragment `key=<key>` (the view) or `delete=<secret>` (the page that deletes it). Nothing else is a
 * share's address: a path of anything else, or a fragment of anything else, is the page's other modes'. The
 * key or secret is as the address spells it, checked only when it is used (`readShareKey`, `isShareSecret`),
 * so a link cut short is still a share's, and says so.
 * @param {string | URL} href  The page's address.
 * @returns {{ id: string, key: string } | { id: string, deleteSecret: string } | null}
 */
export function readShareAddress(href) {
  const address = new URL(String(href));
  const id = address.pathname.slice(1);
  if (!SHARE_ID_PATTERN.test(id)) return null;
  const said = /^(key|delete)=(.*)$/s.exec(address.hash.slice(1));
  if (!said) return null;
  return said[1] === 'key' ? { id, key: said[2] } : { id, deleteSecret: said[2] };
}

/** Whether `text` has a delete or write secret's form (43 base64url characters, 32 bytes). */
export function isShareSecret(text) {
  return SECRET_PATTERN.test(String(text ?? '')) && base64url(text)?.length === 32;
}

/**
 * The 32 bytes of a share's key as its link spells it, or SHARE_UNREADABLE where it is none.
 * @param {string} key
 */
export function readShareKey(key) {
  const bytes = SECRET_PATTERN.test(String(key ?? '')) ? base64url(key) : null;
  if (bytes?.length !== 32) throw unreadable();
  return bytes;
}

/** The archive the stored bytes hold: `IV || ciphertext-and-tag`, decrypted under `key`. */
async function decrypt(stored, key) {
  const raw = readShareKey(key);
  const bytes = stored instanceof Uint8Array ? stored : new Uint8Array(stored);
  if (bytes.byteLength < IV_BYTES + TAG_BYTES) throw unreadable();
  const cryptoKey = await crypto.subtle.importKey('raw', raw, 'AES-GCM', false, ['decrypt']);
  try {
    return new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: bytes.subarray(0, IV_BYTES), tagLength: 128 },
      cryptoKey, bytes.subarray(IV_BYTES)));
  } catch (error) {
    throw unreadable(error);
  }
}

/** `bytes` gunzipped, up to `maxBytes`. */
async function gunzip(bytes, maxBytes, signal) {
  if (bytes[0] !== 0x1f || bytes[1] !== 0x8b) throw unsupported('it is not gzip-compressed.');
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip')).getReader();
  const chunks = [];
  let total = 0;
  try {
    for (;;) {
      checkSignal(signal);
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > maxBytes) throw unsupported(`it holds more than ${maxBytes} bytes.`);
      chunks.push(value);
    }
  } catch (error) {
    void reader.cancel().catch(() => {});
    if (error?.code === SHARE_UNSUPPORTED || error?.name === 'AbortError') throw error;
    throw unsupported('its gzip stream is not whole.', error);
  }
  const whole = new Uint8Array(total);
  let at = 0;
  for (const chunk of chunks) { whole.set(chunk, at); at += chunk.byteLength; }
  return whole;
}

/** A header's text field: its bytes up to the first NUL, as UTF-8. */
function field(header, start, length) {
  const bytes = header.subarray(start, start + length);
  const end = bytes.indexOf(0);
  try {
    return names.decode(end < 0 ? bytes : bytes.subarray(0, end));
  } catch (error) {
    throw unsupported('an entry\'s name is not UTF-8.', error);
  }
}

/** A header's octal number (spaces and NULs around it), or null where it has none. */
function octal(header, start, length) {
  const text = String.fromCharCode(...header.subarray(start, start + length)).replace(/[\0 ]+$/, '').replace(/^ +/, '');
  return /^[0-7]+$/.test(text) ? Number.parseInt(text, 8) : null;
}

/** Whether `path` names a file inside a folder: relative, `/` separated, with no empty, `.` or `..` segment. */
function safePath(path) {
  if (!path || path.startsWith('/') || path.includes('\\') || /^[A-Za-z]:/.test(path)) return false;
  return path.split('/').every(segment => segment !== '' && segment !== '.' && segment !== '..');
}

/**
 * The files a POSIX ustar archive holds, by path (the header's prefix, `/`, then its name). Only regular
 * files are read: a folder, a link, an extended header or any other entry refuses the whole archive, as do
 * an unsafe path, a path twice and a header that is not whole.
 * @param {Uint8Array} bytes
 * @returns {Map<string, Uint8Array>}
 */
function readUstar(bytes) {
  const files = new Map();
  let at = 0;
  for (;;) {
    // The archive's end is a block of zeros (two, as written; one, or none at the very end, is read alike).
    if (at === bytes.length) break;
    if (at + BLOCK > bytes.length) throw unsupported('it ends inside an entry\'s header.');
    const header = bytes.subarray(at, at + BLOCK);
    if (header.every(byte => byte === 0)) break;
    let sum = 0;
    for (let index = 0; index < BLOCK; index += 1) sum += index >= 148 && index < 156 ? 0x20 : header[index];
    if (octal(header, 148, 8) !== sum) throw unsupported('an entry\'s header does not match its checksum.');
    // POSIX ustar's magic and version ("ustar\0", "00"); GNU's "ustar  \0" puts other fields in the prefix's place.
    if (String.fromCharCode(...header.subarray(257, 265)) !== 'ustar\u000000') throw unsupported('it is not a POSIX ustar archive.');
    const name = field(header, 0, 100);
    const prefix = field(header, 345, 155);
    const path = prefix ? `${prefix}/${name}` : name;
    const type = header[156];
    if (type !== 0x30 && type !== 0) {
      throw unsupported(`${JSON.stringify(path)} is no regular file (its entry's type is ${JSON.stringify(String.fromCharCode(type))}).`);
    }
    if (!safePath(path)) throw unsupported(`${JSON.stringify(path)} is no path inside the bundle.`);
    if (files.has(path)) throw unsupported(`${JSON.stringify(path)} is in it twice.`);
    const size = octal(header, 124, 12);
    if (size === null) throw unsupported(`${JSON.stringify(path)} has no size this reader reads.`);
    const start = at + BLOCK;
    if (start + size > bytes.length) throw unsupported(`it ends inside ${JSON.stringify(path)}.`);
    files.set(path, bytes.subarray(start, start + size));
    at = start + Math.ceil(size / BLOCK) * BLOCK;
  }
  if (!files.size) throw unsupported('it holds no files.');
  return files;
}

/**
 * The files of the view bundle a share's stored bytes hold, by path: decrypted under `key` (its link's
 * spelling), gunzipped and read. SHARE_UNREADABLE where the key does not open the bytes, SHARE_UNSUPPORTED
 * where what it opens is no archive this reads.
 * @param {ArrayBuffer | Uint8Array} stored  `IV || ciphertext-and-tag`, as the service answers it.
 * @param {string} key
 * @param {{ signal?: AbortSignal, maxBytes?: number }} [options]
 * @returns {Promise<Map<string, Uint8Array>>}
 */
export async function readShareArchive(stored, key, { signal, maxBytes = SHARE_MAX_BYTES } = {}) {
  checkSignal(signal);
  const archive = await decrypt(stored, key);
  checkSignal(signal);
  return readUstar(await gunzip(archive, maxBytes, signal));
}

/**
 * Open a share's stored bytes as the viewer's service over its bundle: `readShareArchive`, then
 * `openViewBundle(viewBundleMemorySource(files))`. A bundle that does not open (no manifest, another
 * format) is SHARE_UNSUPPORTED, its reason in the message.
 * @param {ArrayBuffer | Uint8Array} stored
 * @param {string} key
 * @param {{ signal?: AbortSignal, maxBytes?: number }} [options]
 * @returns {Promise<import('./types.js').CadViewBundleClient>}
 */
export async function openShareArchive(stored, key, options = {}) {
  const files = await readShareArchive(stored, key, options);
  try {
    return await openViewBundle(viewBundleMemorySource(files), { signal: options.signal });
  } catch (error) {
    if (error?.name === 'AbortError') throw error;
    throw Object.assign(new Error(`This shared model holds no view bundle this viewer opens: ${error?.message || error}`),
      { code: SHARE_UNSUPPORTED, cause: error });
  }
}
