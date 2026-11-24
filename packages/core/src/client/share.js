// A shared view bundle (`cad-share/2`): one document's view bundle (`bundle.js`) kept by a share service, every
// object of it sealed, for a page to open by a link that is the share's address alone:
//
//   https://<service>/<id>                  the view: the page reads the share's manifest, then its packs
//   https://<service>/<id>#delete=<secret>  the page that deletes the share
//
// `<id>` is 16 random bytes and `<secret>` 32, each base64url with no padding (22 and 43 characters). The id is
// the capability: the key the share is sealed with is derived from it (HKDF-SHA256 over the id's text, the salt
// `cad-share/2`, the info `key`), by the service and by the page alone, so no link holds a key and nothing keeps
// one. A stored object is `IV || AES-256-GCM(key, IV, plaintext, AAD)`, the IV 12 bytes and the tag at the end,
// its AAD naming what it is (`cad-share/2 manifest`, `cad-share/2 pack <pack id>`), so neither stands in for the
// other.
//
// A share is two things under one id: the view (the bundle a page draws) and the files that made it (a model's
// script, its modules and the files its build read; a file document's file), which the service serves as a zip
// beside the view (`/<id>.zip`). The share's manifest names the document, and every file of each by its path, with
// its size, its SHA-256 and where its gzip member lies: one or more ranges of packs, joined in order. A pack is
// named by the SHA-256 of its bytes and never changes, so the browser keeps it, and a model shared again fetches
// only the packs it lacks. A file of the view is read here by fetching each pack it names once, opening it,
// joining the ranges, gunzipping them (`DecompressionStream`) and checking the size and the SHA-256; and every pack
// the view names is fetched ahead as soon as the manifest is read, a few at a time, so a whole model arrives at
// full speed while each read takes what has come. Then the bundle opens as any other (`openViewBundle`). The files
// that made it are not the page's: no pack only they name is fetched, and the host is told only what they are.
//
// Failures are told apart by `code`: SHARE_DAMAGED, a manifest that does not open or is not one, or a file that is
// not what the manifest says (a pack that does not open, a range past its end, bytes that are no gzip member or not
// the file's size or SHA-256); SHARE_UNAVAILABLE, a pack the service did not give, which may pass; SHARE_UNSUPPORTED,
// a bundle this viewer does not open (another layout). What the service answers for the manifest (a share it has
// none of, a refusal) is the host's read's own failure, passed on as it is.

import { openViewBundle, VIEW_BUNDLE_MANIFEST } from './bundle.js';

/** The one format this reader reads: a share's manifest of another is refused, as a damaged link. */
export const SHARE_FORMAT = 'cad-share/2';
/** A share's id: 16 random bytes, base64url without padding. */
export const SHARE_ID_PATTERN = /^[A-Za-z0-9_-]{22}$/;
/** The most packs fetched at a time, ahead of the reads or for them. */
export const SHARE_PREFETCH = 6;
/** A manifest that does not open or is not one, or a file not as it says: the link is damaged. */
export const SHARE_DAMAGED = 'share-damaged';
/** A pack the service did not give (no network, a refusal, none by that id): reading it again may work. */
export const SHARE_UNAVAILABLE = 'share-unavailable';
/** A share whose bundle this viewer does not open. */
export const SHARE_UNSUPPORTED = 'share-unsupported';

// A delete or write secret: 32 random bytes, base64url without padding.
const SECRET_PATTERN = /^[A-Za-z0-9_-]{43}$/;
const HEX_SHA256 = /^[0-9a-f]{64}$/;
// What a share's manifest holds, and nothing else.
const MANIFEST_MEMBERS = new Set(['format', 'name', 'entry', 'made', 'view', 'files']);
// A manifest's limits: the files it lists over both its maps, a path's length, the document's name in characters,
// and what built a model: so many members, each name and value so many characters.
const MAX_FILES = 200_000;
const MAX_PATH_BYTES = 1024;
const MAX_NAME = 200;
const MAX_MADE = 32;
const MAX_MADE_TEXT = 100;
const IV_BYTES = 12;
const TAG_BYTES = 16;
const MANIFEST_AAD = `${SHARE_FORMAT} manifest`;
const encoder = new TextEncoder();
const text = new TextDecoder('utf-8', { fatal: true });

const damaged = (detail, cause) => Object.assign(new Error(`This link is damaged: ${detail}`),
  { code: SHARE_DAMAGED, ...(cause ? { cause } : {}) });
const abortError = () => new DOMException('The operation was aborted.', 'AbortError');
function checkSignal(signal) { if (signal?.aborted) throw abortError(); }
const isObject = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const isCount = value => Number.isSafeInteger(value) && value >= 0;
const isDigest = value => typeof value === 'string' && HEX_SHA256.test(value);
/** Whether `value` is text (no lone surrogate) of `least` to `most` characters, each counted as one code point. */
function isText(value, least, most) {
  // A code point is at most two UTF-16 units: a string longer than twice `most` has more than `most` of them.
  if (typeof value !== 'string' || value.length > 2 * most || /\p{Cs}/u.test(value)) return false;
  const characters = [...value].length;
  return characters >= least && characters <= most;
}
/** A value as a refusal names it: in JSON, cut short where it is long. */
const quote = value => (JSON.stringify(typeof value === 'string' ? value.slice(0, 80) : value) ?? 'nothing').slice(0, 80);
const hex = bytes => Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, '0')).join('');

/** Base64url without padding as bytes, or null where it is none. */
function base64url(value) {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]*$/.test(value) || value.length % 4 === 1) return null;
  const binary = atob(value.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat((4 - (value.length % 4)) % 4));
  return Uint8Array.from(binary, char => char.charCodeAt(0));
}

/**
 * What a page's address says of a share, or null where it names none: its path exactly one share id, and its
 * fragment `delete=<secret>` (the page that deletes it) or anything else (the view: the address alone opens it, so
 * a fragment it once carried, such as a key, is passed over). A path of anything else is the page's other modes'.
 * The secret is as the address spells it, checked only when it is used (`isShareSecret`).
 * @param {string | URL} href  The page's address.
 * @returns {{ id: string } | { id: string, deleteSecret: string } | null}
 */
export function readShareAddress(href) {
  const address = new URL(String(href));
  const id = address.pathname.slice(1);
  if (!SHARE_ID_PATTERN.test(id)) return null;
  const said = /^delete=(.*)$/s.exec(address.hash.slice(1));
  return said ? { id, deleteSecret: said[1] } : { id };
}

/** Whether `value` has a delete or write secret's form (43 base64url characters, 32 bytes). */
export function isShareSecret(value) {
  return SECRET_PATTERN.test(String(value ?? '')) && base64url(value)?.length === 32;
}

/**
 * 32 bytes derived from share `id` with HKDF-SHA256: the input the UTF-8 bytes of the id's text, the salt those of
 * `cad-share/2`, the info those of `info`: `key`, the AES-256-GCM key the share is sealed with, or `name`, the
 * share's storage name at its service (written as hex).
 * @param {string} id
 * @param {'key' | 'name'} info
 * @returns {Promise<Uint8Array>}
 */
export async function deriveShareBits(id, info) {
  const input = await crypto.subtle.importKey('raw', encoder.encode(id), 'HKDF', false, ['deriveBits']);
  return new Uint8Array(await crypto.subtle.deriveBits({ name: 'HKDF', hash: 'SHA-256', salt: encoder.encode(SHARE_FORMAT),
    info: encoder.encode(info) }, input, 256));
}

/** The plaintext of a sealed object (`IV || ciphertext-and-tag`) with its `aad`, or SHARE_DAMAGED saying `what` did not open. */
async function unseal(key, sealed, aad, what) {
  const bytes = sealed instanceof Uint8Array ? sealed : new Uint8Array(sealed);
  if (bytes.byteLength < IV_BYTES + TAG_BYTES) throw damaged(`${what} does not open.`);
  try {
    return new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: bytes.subarray(0, IV_BYTES),
      additionalData: encoder.encode(aad), tagLength: 128 }, key, bytes.subarray(IV_BYTES)));
  } catch (error) {
    throw damaged(`${what} does not open.`, error);
  }
}

/** Whether `path` names a file inside a folder: relative, `/` separated, no empty, `.` or `..` segment, not too long. */
function relativePath(path) {
  if (!path || path.startsWith('/') || path.includes('\\') || /^[A-Za-z]:/.test(path)) return false;
  if (encoder.encode(path).byteLength > MAX_PATH_BYTES) return false;
  return path.split('/').every(segment => segment !== '' && segment !== '.' && segment !== '..');
}

/**
 * The share's manifest this reader believes, and nothing else, each refusal a damaged link saying what: its
 * `format` this reader's; its document's `name` (1 to 200 characters of text, no control character); for a model
 * its script (`entry`, the path of one of its `files`) and what built it (`made`: at most 32 members, each name and
 * value at most 100 characters of text), each null for a file document; and two maps of files by their paths, the
 * view bundle's (`view`, `manifest.json` among them) and the files that made it (`files`, which may be none), each
 * file with its SHA-256, its size and the ranges of packs that hold its gzip member, at most 200,000 over both.
 * @returns {import('./types.js').ShareManifest}
 */
function readShareManifest(value) {
  if (!isObject(value)) throw damaged("the share's manifest is not an object.");
  if (value.format !== SHARE_FORMAT) throw damaged(`the share's manifest is ${JSON.stringify(value.format ?? null)}, not ${SHARE_FORMAT}.`);
  const other = Object.keys(value).find(member => !MANIFEST_MEMBERS.has(member));
  if (other !== undefined) throw damaged(`the share's manifest holds ${quote(other)}, which a share's manifest does not.`);
  const { name, entry, made, view, files } = value;
  if (!isObject(view)) throw damaged("the share's manifest has no view.");
  if (!isObject(files)) throw damaged("the share's manifest lists no files that made it.");
  if (!isText(name, 1, MAX_NAME) || /\p{Cc}/u.test(name)) {
    throw damaged(`the share's manifest names its document ${quote(name)}, not 1 to ${MAX_NAME} characters of text.`);
  }
  if (entry !== null && !(typeof entry === 'string' && Object.hasOwn(files, entry))) {
    throw damaged(`the share's manifest names ${quote(entry)} as its script, which is none of the files that made it.`);
  }
  if (made !== null && !(isObject(made) && Object.keys(made).length <= MAX_MADE
    && Object.entries(made).every(([what, release]) => isText(what, 0, MAX_MADE_TEXT) && isText(release, 0, MAX_MADE_TEXT)))) {
    throw damaged(`the share's manifest says what built it as ${quote(made)}, not at most ${MAX_MADE} names and values of ${MAX_MADE_TEXT} characters.`);
  }
  const maps = [[view, 'its view', 'a bundle'], [files, 'the files that made it', 'a folder']];
  const count = maps.reduce((sum, [map]) => sum + Object.keys(map).length, 0);
  if (count > MAX_FILES) throw damaged(`the share's manifest lists ${count} files, more than ${MAX_FILES}.`);
  if (!Object.hasOwn(view, VIEW_BUNDLE_MANIFEST)) throw damaged(`the share's manifest lists no ${VIEW_BUNDLE_MANIFEST} in its view.`);
  for (const [map, where, inside] of maps) {
    for (const [path, file] of Object.entries(map)) {
      if (!relativePath(path)) throw damaged(`the share's manifest names ${quote(path)} in ${where}, which is no path inside ${inside}.`);
      const ranges = isObject(file) ? file.at : null;
      if (!isDigest(file?.sha256) || !isCount(file.bytes) || !Array.isArray(ranges) || !ranges.length
        || !ranges.every(range => Array.isArray(range) && range.length === 3 && isDigest(range[0]) && isCount(range[1]) && isCount(range[2]))) {
        throw damaged(`the share's manifest gives ${quote(path)} in ${where} no SHA-256, size and ranges of packs.`);
      }
    }
  }
  return value;
}

/** `promise`, which others share: `signal` stops this asker waiting for it, and leaves it to them. */
function abandonable(promise, signal) {
  if (!signal) return promise;
  return new Promise((resolve, reject) => {
    const stop = () => reject(abortError());
    if (signal.aborted) { stop(); return; }
    signal.addEventListener('abort', stop, { once: true });
    promise.then(resolve, reject).finally(() => signal.removeEventListener('abort', stop));
  });
}

/** The file `path` whose gzip member is `ranges`, joined: exactly `size` bytes, or SHARE_DAMAGED. */
async function gunzip(ranges, size, path, signal) {
  const reader = new Blob(ranges).stream().pipeThrough(new DecompressionStream('gzip')).getReader();
  const file = new Uint8Array(size);
  let at = 0;
  try {
    for (;;) {
      checkSignal(signal);
      const { done, value } = await reader.read();
      if (done) break;
      if (value.byteLength > size - at) throw damaged(`${path} holds more than the ${size} bytes the share's manifest says.`);
      file.set(value, at);
      at += value.byteLength;
    }
  } catch (error) {
    void reader.cancel().catch(() => {});
    if (error?.code === SHARE_DAMAGED || error?.name === 'AbortError') throw error;
    throw damaged(`${path} is no whole gzip member.`, error);
  }
  if (at !== size) throw damaged(`${path} is ${at} bytes; the share's manifest says ${size}.`);
  return file;
}

/**
 * The bundle a share holds, as a view bundle's source: each path of the share's `view` (its manifest's map of the
 * bundle's files), read from the packs that hold it (`pack`, the service's read of one, sealed), opened with `key`.
 * Each pack is fetched once and kept while the source is (a pack that did not come is asked for again by the next
 * read of it); from the start, every pack the view names is fetched ahead, and no other, the ones holding
 * `manifest.json` and `structure.json` first, SHARE_PREFETCH at a time, and a read's packs go to the head of the
 * line. `dispose()` stops what is under way and lets the packs go.
 * @param {import('./types.js').ShareManifest['view']} view
 * @param {{ key: CryptoKey, pack: import('./types.js').ShareService['pack'] }} options
 * @returns {import('./types.js').ViewBundleSource}
 */
function viewBundleShareSource(view, { key, pack: fetchPack }) {
  const lifetime = new AbortController();
  /** Each pack asked for, by its id: its bytes, opened, once they come. */
  const packs = new Map();
  /** The packs asked for and not yet fetched, in the order they will be. */
  const line = [];
  let fetching = 0;

  function held(id) {
    let pack = packs.get(id);
    if (!pack) {
      let settle;
      const bytes = new Promise((resolve, reject) => { settle = { resolve, reject }; });
      // A pack fetched ahead that nothing reads yet fails no one.
      bytes.catch(() => {});
      pack = { bytes, settle, started: false };
      packs.set(id, pack);
    }
    return pack;
  }
  function start(id, pack) {
    pack.started = true;
    fetching += 1;
    (async () => unseal(key, await fetchPack(id, { signal: lifetime.signal }), `${SHARE_FORMAT} pack ${id}`, `the pack ${id}`))()
      .then(pack.settle.resolve, error => {
        if (packs.get(id) === pack) packs.delete(id);
        pack.settle.reject(error);
      })
      .finally(() => { fetching -= 1; pump(); });
  }
  function pump() {
    while (fetching < SHARE_PREFETCH && line.length && !lifetime.signal.aborted) {
      const id = line.shift();
      const pack = packs.get(id);
      if (pack && !pack.started) start(id, pack);
    }
  }
  /** The opened bytes of each of the packs `ids`, in order; `first`, ahead of the line. */
  function want(ids, first) {
    const wanted = ids.map(held);
    const waiting = ids.filter((id, index) => !wanted[index].started);
    for (const id of waiting) { const at = line.indexOf(id); if (at >= 0) line.splice(at, 1); }
    if (first) line.unshift(...waiting); else line.push(...waiting);
    pump();
    return wanted.map(pack => pack.bytes);
  }
  const packsOf = path => (Object.hasOwn(view, path) ? view[path].at.map(([id]) => id) : []);
  want([...new Set([...packsOf(VIEW_BUNDLE_MANIFEST), ...packsOf('structure.json'), ...Object.keys(view).flatMap(packsOf)])], false);

  return {
    async read(path, { signal } = {}) {
      checkSignal(signal);
      if (lifetime.signal.aborted) throw abortError();
      const entry = Object.hasOwn(view, path) ? view[path] : null;
      if (!entry) throw Object.assign(new Error(`This shared model holds no ${path}.`), { status: 404 });
      const ids = [...new Set(entry.at.map(([id]) => id))];
      const opened = new Map();
      try {
        const bytes = await Promise.all(want(ids, true).map(promise => abandonable(promise, signal)));
        ids.forEach((id, index) => opened.set(id, bytes[index]));
      } catch (error) {
        if (error?.name === 'AbortError' || error?.code === SHARE_DAMAGED) throw error;
        throw Object.assign(new Error(`This shared model's ${path} could not be fetched: ${error?.message || error}`),
          { code: SHARE_UNAVAILABLE, cause: error });
      }
      const ranges = entry.at.map(([id, offset, length]) => {
        const bytes = opened.get(id);
        if (offset + length > bytes.byteLength) throw damaged(`${path} lies past the end of the pack ${id}.`);
        return bytes.subarray(offset, offset + length);
      });
      const file = await gunzip(ranges, entry.bytes, path, signal);
      if (hex(await crypto.subtle.digest('SHA-256', file)) !== entry.sha256) {
        throw damaged(`${path} is not the file the share's manifest names: its SHA-256 differs.`);
      }
      return file.buffer;
    },
    dispose() {
      if (lifetime.signal.aborted) return;
      lifetime.abort();
      line.length = 0;
      for (const pack of packs.values()) if (!pack.started) pack.settle.reject(abortError());
      packs.clear();
    },
  };
}

/**
 * Open share `id` as the viewer's service over its view: its key derived from the id, its manifest read
 * (`service.manifest`) and opened, then its view bundle read from its packs (`service.pack`), fetched ahead from
 * the start, and opened as any other (`openViewBundle`). The service also says what the share holds beside its view
 * (`share`): its document's name, a model's script and what built it, and the paths of the files that made it,
 * which the share's zip holds; none of their packs is fetched. SHARE_DAMAGED where the manifest does not open or is
 * not one, or a file is not as it says; SHARE_UNAVAILABLE where a pack did not come; SHARE_UNSUPPORTED where the
 * bundle is one this viewer does not open; a failure of `service.manifest` as it is. Disposing the service stops
 * the share's fetches and lets its packs go.
 * @param {string} id
 * @param {import('./types.js').ShareService} service
 * @param {{ signal?: AbortSignal }} [options]
 * @returns {Promise<import('./types.js').CadShareClient>}
 */
export async function openShare(id, service, { signal } = {}) {
  if (!SHARE_ID_PATTERN.test(String(id))) throw damaged('it names no share.');
  checkSignal(signal);
  const key = await crypto.subtle.importKey('raw', await deriveShareBits(id, 'key'), 'AES-GCM', false, ['decrypt']);
  const sealed = await service.manifest({ signal });
  checkSignal(signal);
  const plain = await unseal(key, sealed, MANIFEST_AAD, "the share's manifest");
  let parsed;
  try { parsed = JSON.parse(text.decode(plain)); } catch (error) { throw damaged("the share's manifest is not JSON.", error); }
  const manifest = readShareManifest(parsed);
  const source = viewBundleShareSource(manifest.view, { key, pack: (pack, options) => service.pack(pack, options) });
  let client;
  try {
    client = await openViewBundle(source, { signal });
  } catch (error) {
    source.dispose?.();
    // The source's own failures say what they are; whatever else stops the bundle opening is the bundle's.
    if (error?.name === 'AbortError' || error?.code === SHARE_DAMAGED || error?.code === SHARE_UNAVAILABLE) throw error;
    throw Object.assign(new Error(`This shared model holds no view bundle this viewer opens: ${error?.message || error}`),
      { code: SHARE_UNSUPPORTED, cause: error });
  }
  const { name, entry, made, files } = manifest;
  return Object.assign(client, { share: Object.freeze({ name, entry, made: made && Object.freeze({ ...made }),
    files: Object.freeze(Object.keys(files)) }) });
}
