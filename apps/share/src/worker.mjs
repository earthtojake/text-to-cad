// The share service: a Cloudflare Worker over an R2 bucket (SHARES), the viewer's static assets (ASSETS)
// and two rate limiters (LIMITER for commits and deletes, LIMITER_PACKS for packs and zips). Its API,
// storage, pages and zip are README.md's; this file is the whole of the service, and `serve.mjs` runs this
// same module locally over Node's http.
//
// A share's id is the capability. The AES-256-GCM key its objects are sealed with, and the name it is
// stored under, are derived from the id here, for one request, and dropped with it. Nothing here logs,
// stores or puts in an error an id, a key or a secret: the bucket holds a share under its derived name,
// and each secret as its SHA-256 alone.

export const FORMAT = "cad-share/2";
export const HOME = "https://www.texttocad.dev";
/** The deployment's variables (wrangler.jsonc, `vars`), where it sets none or one that is no positive number. */
export const DEFAULTS = Object.freeze({
  MAX_PACK_BYTES: 8 * 1024 * 1024,
  MAX_MANIFEST_BYTES: 16 * 1024 * 1024,
  MAX_SHARE_BYTES: 256 * 1024 * 1024,
  EXPIRY_DAYS: 7,
});
/** The most files a share manifest lists, its view's and its files' together. */
export const MAX_FILES = 200_000;
/** The age at which the bucket's lifecycle rule deletes an object, counted from its upload (README.md,
 * "Set-up, once"). A commit stores again what its share keeps that the rule would take before it expires. */
export const BACKSTOP_DAYS = 8;
// Both limiters count per minute (wrangler.jsonc, `simple.period`), so a refused client waits that.
export const RETRY_AFTER_SECONDS = 60;

const ID = /^[A-Za-z0-9_-]{22}$/;
const SECRET = /^[A-Za-z0-9_-]{43}$/;
const HEX_SHA256 = /^[0-9a-f]{64}$/;
const BEARER = /^Bearer ([^\s]+)$/;
const API = /^\/v1\/shares\/([^/]*)(?:\/packs\/([^/]*))?$/;
const ZIP = /^\/([A-Za-z0-9_-]{22})\.zip$/;
const MAX_PATH_BYTES = 1024;
const IV_BYTES = 12;
const TAG_BYTES = 16;
const DAY_MS = 24 * 60 * 60 * 1000;
// R2 deletes at most 1000 keys a call. A Worker holds six connections at once, so four calls at a time
// leave room for the request's own.
const DELETE_BATCH = 1000;
const AT_ONCE = 4;
const MANIFEST_AAD = `${FORMAT} manifest`;
const packAad = (pack) => `${FORMAT} pack ${pack}`;
const UTF8 = new TextEncoder();
const STRICT_UTF8 = new TextDecoder("utf-8", { fatal: true });

// The page's content security policy: the viewer fetches from its own origin only. Each inline
// script of the HTML served is allowed by its hash (`pageHeaders`), never by 'unsafe-inline': the
// viewer's index.html carries two, its first-paint appearance and the build's table of chunk ids.
const CSP = {
  "default-src": ["'self'"],
  // 'wasm-unsafe-eval': the viewer's mesh decoders compile WebAssembly.
  "script-src": ["'self'", "'wasm-unsafe-eval'"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:", "blob:"],
  "font-src": ["'self'", "data:"],
  "connect-src": ["'self'", "data:", "blob:"],
  "worker-src": ["'self'", "blob:"],
  "frame-ancestors": ["'none'"],
  "base-uri": ["'none'"],
  "form-action": ["'none'"],
};

export default {
  fetch(request, env, ctx) {
    return handle(request, env);
  },
};

/** The service. `now` is the clock, in milliseconds, which the tests set. */
export async function handle(request, env, { now = Date.now } = {}) {
  const response = await answer(request, env, now);
  // Every answer, a page's, a file's or the API's: no share is for a search engine.
  response.headers.set("X-Robots-Tag", "noindex, nofollow");
  return response;
}

async function answer(request, env, now) {
  const url = new URL(request.url);
  const path = url.pathname;
  if (path === "/v1" || path.startsWith("/v1/")) return api(request, env, path, now);
  if (path === "/") {
    if (!isRead(request)) return notAllowed("GET, HEAD");
    return new Response(null, { status: 302, headers: { Location: HOME, "Cache-Control": "no-store" } });
  }
  const zip = ZIP.exec(path);
  if (zip) return readZip(request, env, zip[1], now);
  if (ID.test(path.slice(1))) {
    // A share's page: the viewer, whatever the fragment (which never reaches this code).
    if (!isRead(request)) return notAllowed("GET, HEAD");
    const index = await env.ASSETS.fetch(new Request(new URL("/index.html", url), { method: "GET" }));
    if (!index.ok) return refuse(404, "not_found", "The viewer is not deployed with this service.");
    return page(request, index);
  }
  return asset(request, env);
}

// ---- the API --------------------------------------------------------------------------------------

async function api(request, env, path, now) {
  const match = API.exec(path);
  if (!match) return refuse(404, "not_found", "The API's routes are /v1/shares/<id> and /v1/shares/<id>/packs/<pack id>.");
  const [, id, pack] = match;
  if (!ID.test(id)) return refuse(400, "bad_id", "A share id is 22 characters of base64url.");
  if (pack !== undefined) {
    if (!HEX_SHA256.test(pack)) {
      return refuse(400, "bad_pack_id", "A pack id is the lowercase hex SHA-256 of the pack's bytes.");
    }
    switch (request.method) {
      case "PUT": return putPack(request, env, id, pack, settingsOf(env));
      case "GET": case "HEAD": return readPack(request, env, id, pack, now);
      default: return notAllowed("PUT, GET, HEAD");
    }
  }
  switch (request.method) {
    case "PUT": return commit(request, env, id, settingsOf(env), now);
    case "GET": case "HEAD": return readManifest(request, env, id, now);
    case "DELETE": return remove(request, env, id);
    default: return notAllowed("PUT, GET, HEAD, DELETE");
  }
}

async function putPack(request, env, id, pack, settings) {
  const writer = writerOf(request);
  if (writer.refusal) return writer.refusal;
  const length = lengthOf(request);
  if (length === null) return lengthRequired();
  if (length > settings.maxPackBytes) return tooLarge(`A pack is at most ${settings.maxPackBytes} bytes.`);
  if (!(await allowed(env.LIMITER_PACKS, request))) return limited("pack uploads and zips");

  const place = await placeOf(id);
  const writeHash = await sha256Hex(writer.secret);
  // A share another write secret holds is refused before its body is read.
  const found = await env.SHARES.head(place.owner);
  if (found && !ownedBy(found, writeHash)) return forbidden();
  const body = await readAtMost(request, length, settings.maxPackBytes);
  if (body === null) return tooLarge(`A pack is at most ${settings.maxPackBytes} bytes.`);
  if (await sha256Hex(body) !== pack) return refuse(400, "bad_pack", "The body's SHA-256 is not its pack id.");
  if (!found && !(await claim(env, place, writeHash, writer.deleteHash))) return forbidden();

  // Stored again, a pack is the same bytes under a fresh IV: harmless, and it starts the backstop's count again.
  const stored = await seal(await keyOf(id), body, packAad(pack));
  await env.SHARES.put(`${place.packs}${pack}`, stored, { httpMetadata: { contentType: "application/octet-stream" } });
  return json(201, { pack, bytes: stored.byteLength });
}

async function commit(request, env, id, settings, now) {
  const writer = writerOf(request);
  if (writer.refusal) return writer.refusal;
  const length = lengthOf(request);
  if (length === null) return lengthRequired();
  if (length > settings.maxManifestBytes) return tooLarge(`A share manifest is at most ${settings.maxManifestBytes} bytes.`);
  if (!(await allowed(env.LIMITER, request))) return limited("commits and deletes");
  const body = await readAtMost(request, length, settings.maxManifestBytes);
  if (body === null) return tooLarge(`A share manifest is at most ${settings.maxManifestBytes} bytes.`);
  const manifest = checkManifest(body);
  if (manifest.problem) return refuse(400, "bad_manifest", manifest.problem);

  const place = await placeOf(id);
  const writeHash = await sha256Hex(writer.secret);
  const found = await env.SHARES.head(place.owner);
  const owner = found ? (ownedBy(found, writeHash) ? found : null) : await claim(env, place, writeHash, writer.deleteHash);
  if (!owner) return forbidden();

  // The manifest this one replaces. The put below is conditional on it, and a live one's packs are kept one
  // commit more, for a page that opened it and is still fetching them. An expired one is no share's: its
  // packs are not kept, and this commit makes the share anew (201).
  const key = await keyOf(id);
  const current = await env.SHARES.get(place.manifest);
  const live = current !== null && !expired(current, now);
  const kept = live ? await packsNamedBy(current, key) : new Set();
  if (current && !live) await current.body.cancel();

  const stored = new Map();
  for (const object of await listAll(env, place.packs)) {
    const pack = object.key.slice(place.packs.length);
    if (HEX_SHA256.test(pack)) stored.set(pack, object);
  }
  const missing = [...manifest.packs.keys()].filter((pack) => !stored.has(pack)).sort();
  if (missing.length) {
    const hint = "This share holds no pack of these ids: upload them, then commit again.";
    return json(409, { error: "missing_packs", hint, missing });
  }
  let bytes = 0;
  for (const [pack, end] of manifest.packs) {
    const size = stored.get(pack).size;
    if (end > size - IV_BYTES - TAG_BYTES) return refuse(400, "bad_manifest", `A range runs past the end of pack ${pack}.`);
    bytes += size;
  }
  if (bytes > settings.maxShareBytes) {
    return refuse(413, "share_too_large",
                  `The packs this manifest names hold ${bytes} bytes; a share holds at most ${settings.maxShareBytes}.`);
  }

  const until = now() + settings.expiryDays * DAY_MS;
  const expires = new Date(until).toISOString();
  await keepFromBackstop(env, place, owner, [...manifest.packs.keys()].map((pack) => stored.get(pack)), until);
  const put = await env.SHARES.put(place.manifest, await seal(key, body, MANIFEST_AAD), {
    onlyIf: current ? { etagMatches: current.etag } : new Headers({ "If-None-Match": "*" }),
    httpMetadata: { contentType: "application/octet-stream" },
    customMetadata: { format: FORMAT, expires, bytes: String(bytes), files: String(manifest.files) },
  });
  if (!put) {
    return refuse(409, "conflict", "Another commit replaced this share's manifest while this one was checked. Commit again.");
  }

  const unnamed = [...stored.keys()].filter((pack) => !manifest.packs.has(pack) && !kept.has(pack));
  await removeKeys(env, unnamed.map((pack) => `${place.packs}${pack}`));
  return json(live ? 200 : 201, { id, expires, bytes, files: manifest.files });
}

async function readManifest(request, env, id, now) {
  const place = await placeOf(id);
  const object = request.method === "HEAD" ? await env.SHARES.head(place.manifest) : await env.SHARES.get(place.manifest);
  if (!object) return gone();
  if (expired(object, now)) {
    await object.body?.cancel();
    await deleteShare(env, place);
    return gone();
  }
  return new Response(request.method === "HEAD" ? null : object.body, {
    status: 200,
    headers: {
      "Content-Type": "application/octet-stream",
      "Content-Length": String(object.size),
      "Cache-Control": "no-store",
      "Cad-Share-Expires": object.customMetadata.expires,
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function readPack(request, env, id, pack, now) {
  const place = await placeOf(id);
  const key = `${place.packs}${pack}`;
  // The pack is asked for beside the manifest it needs, not after it.
  const [manifest, object] = await Promise.all([
    env.SHARES.head(place.manifest),
    request.method === "HEAD" ? env.SHARES.head(key) : env.SHARES.get(key),
  ]);
  if (!manifest || expired(manifest, now)) {
    await object?.body?.cancel();
    if (manifest) await deleteShare(env, place);
    return gone();
  }
  if (!object) return refuse(404, "not_found", "This share holds no pack of this id.");
  return new Response(request.method === "HEAD" ? null : object.body, {
    status: 200,
    headers: {
      "Content-Type": "application/octet-stream",
      "Content-Length": String(object.size),
      // Named by its content: what a pack id names never changes.
      "Cache-Control": "private, max-age=604800, immutable",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

async function remove(request, env, id) {
  const bearer = bearerOf(request, "delete secret");
  if (bearer.refusal) return bearer.refusal;
  if (!(await allowed(env.LIMITER, request))) return limited("commits and deletes");
  const place = await placeOf(id);
  const owner = await env.SHARES.head(place.owner);
  if (!owner) return gone();
  const hash = await sha256Hex(bearer.secret);
  const kept = owner.customMetadata ?? {};
  if (!sameHex(kept.delete, hash) && !sameHex(kept.write, hash)) {
    return refuse(403, "forbidden", "This secret is neither the share's delete secret nor its write secret.");
  }
  await deleteShare(env, place);
  return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
}

// ---- the files' zip -------------------------------------------------------------------------------

/** `GET /<id>.zip` (and `HEAD`): the files that made the share, as a zip of one folder named for it. It counts
 * as a pack in LIMITER_PACKS; it is 404 as the share's other reads are. */
async function readZip(request, env, id, now) {
  if (!isRead(request)) return notAllowed("GET, HEAD");
  if (!(await allowed(env.LIMITER_PACKS, request))) return limited("pack uploads and zips");
  const place = await placeOf(id);
  const object = await env.SHARES.get(place.manifest);
  if (!object) return gone();
  if (expired(object, now)) {
    await object.body.cancel();
    await deleteShare(env, place);
    return gone();
  }
  const key = await keyOf(id);
  const plain = await open(key, new Uint8Array(await object.arrayBuffer()), MANIFEST_AAD);
  let manifest = null;
  try {
    manifest = JSON.parse(STRICT_UTF8.decode(plain));
  } catch {
    // Not a manifest this service keeps: no share.
  }
  // One an earlier service kept, of the bundle alone, has no view, and no files to give.
  if (!isObject(manifest) || !isObject(manifest.view) || !isObject(manifest.files)) return gone();

  const folder = safeName(typeof manifest.name === "string" ? manifest.name : "");
  const headers = {
    "Content-Type": "application/zip",
    "Content-Disposition": `attachment; filename="${folder}.zip"`,
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
  };
  if (typeof manifest.entry === "string") headers["Cad-Share-Entry"] = headerText(manifest.entry);
  const made = isObject(manifest.made) ? Object.entries(manifest.made) : [];
  if (made.length) headers["Cad-Share-Made"] = made.map(([name, value]) => `${headerText(name)}=${headerText(value)}`).join(", ");
  if (request.method === "HEAD") return new Response(null, { status: 200, headers });
  return new Response(zipOf(folder, Object.entries(manifest.files), packReader(env, place, key)), { status: 200, headers });
}

/** The share's name as a file's and a folder's: letters, digits, `.`, `-` and `_` kept and every other
 * character `_`, no `.` at either end (so no `.` or `..` folder), at most 100 characters; `share` where
 * nothing is left. */
function safeName(name) {
  const kept = Array.from(name, (character) => (/^[A-Za-z0-9._-]$/.test(character) ? character : "_")).join("");
  return kept.replace(/^\.+/, "").slice(0, 100).replace(/\.+$/, "") || "share";
}

/** Text as a header carries it (Cad-Share-Entry, each name and value of Cad-Share-Made): its UTF-8, every byte
 * but a letter, a digit and `-._~/+` written `%XX` (RFC 3986), so that any text travels, and `,` and `=` part
 * the members. What holds none of those travels as it is; a percent-decoder reads any back. */
function headerText(text) {
  let written = "";
  for (const byte of UTF8.encode(text)) {
    const character = String.fromCharCode(byte);
    written += /^[A-Za-z0-9._~/+-]$/.test(character) ? character : `%${byte.toString(16).toUpperCase().padStart(2, "0")}`;
  }
  return written;
}

/** A share's packs as its zip reads them: each fetched and opened when first asked for, the two last asked for
 * kept, so a zip holds two packs at most, whatever the share's size. A pack that is not stored or does not
 * open fails the read, and with it the zip. */
function packReader(env, place, key) {
  const held = new Map();
  return (pack) => {
    let opened = held.get(pack);
    if (opened) {
      held.delete(pack);
    } else {
      opened = (async () => {
        const object = await env.SHARES.get(`${place.packs}${pack}`);
        const plain = object && await open(key, new Uint8Array(await object.arrayBuffer()), packAad(pack));
        if (!plain) throw new Error("A pack the share's files name is not stored, or does not open.");
        return plain;
      })();
    }
    held.set(pack, opened);
    while (held.size > PACKS_HELD) held.delete(held.keys().next().value);
    return opened;
  };
}

// ---- the zip format (APPNOTE.TXT, PKWARE's .ZIP File Format Specification) --------------------------

/** The values at which a zip's 4-byte sizes and offsets, and its 2-byte count of entries, no longer hold what
 * they say: from there the field holds its most (0xFFFFFFFF, 0xFFFF), which says "see Zip64", and a Zip64
 * record holds the value. The tests lower them, to write every Zip64 record for a small zip. */
export const ZIP64 = Object.freeze({ size: 0xFFFFFFFF, count: 0xFFFF });
const PACKS_HELD = 2;
// A gzip member's header in the plain form (RFC 1952: ID1, ID2, CM 8, FLG 0, MTIME, XFL, OS), and its trailer
// (CRC32, ISIZE).
const GZIP_HEADER = 10;
const GZIP_TRAILER = 8;
const STORED = 0;
const DEFLATED = 8;
const UTF8_NAMES = 1 << 11;
const VERSION = 20; // 2.0: deflate, folders
const VERSION_ZIP64 = 45; // 4.5
// Every entry's time: 1980-01-01 00:00, the earliest an MS-DOS date holds, so a share's zip is the same each time.
const DOS_TIME = 0;
const DOS_DATE = (1 << 5) | 1;
// Made on UNIX (3), so a reader takes the modes the external attributes hold: rw-r--r-- for a file, and
// rwxr-xr-x for the folder, which also holds the MS-DOS directory bit.
const MADE_ON_UNIX = 3 << 8;
const FILE_ATTRIBUTES = 0o100644 * 0x10000;
const FOLDER_ATTRIBUTES = 0o40755 * 0x10000 + 0x10;
// The zip goes out in pieces of this many bytes, each a copy of its own.
const ZIP_CHUNK = 64 * 1024;

/** The zip of `files` (a manifest's `[path, entry]`s) under one folder, `folder`: the folder's entry, then each
 * file's, sorted by path (by its UTF-8 bytes), each named in UTF-8 and dated 1980-01-01 00:00; then the central
 * directory. A file's gzip member is the zip's data as it is, never compressed again: its deflate stream, with
 * the CRC-32 and size of its trailer (method 8); a member not of the plain form the command writes is inflated
 * and stored (method 0) with its CRC-32 computed. `read(pack)` resolves to a pack's bytes, opened. Zip64 where a
 * size, an offset or the count needs it. A stream of the zip's bytes, made as it is read; it fails where a pack
 * cannot be read or a member does not inflate. */
export function zipOf(folder, files, read, limits = ZIP64) {
  const chunks = zipChunks(folder, files, read, limits);
  return new ReadableStream({
    async pull(controller) {
      const { done, value } = await chunks.next();
      if (done) controller.close();
      else controller.enqueue(value);
    },
    async cancel() {
      await chunks.return();
    },
  }, { highWaterMark: 0 });
}

async function* zipChunks(folder, files, read, limits) {
  const out = new Chunks();
  const written = [];
  let offset = 0;
  // The local header of `file`, its offset and sizes kept for the central directory.
  const begin = (file) => {
    const header = localHeader({ ...file, offset }, limits);
    written.push({ ...file, offset });
    offset += header.byteLength + file.compressed;
    return header;
  };

  // (Each chunk is yielded from a plain loop: in an async generator, `yield*` and `for await` over what is at hand
  // would cost a promise a step, and a share's zip may hold 200,000 files.)
  const folderEntry = { name: UTF8.encode(`${folder}/`), method: STORED, crc: 0, compressed: 0, size: 0, folder: true };
  for (const chunk of out.add(begin(folderEntry))) yield chunk;
  const sorted = files.map(([path, entry]) => ({ name: UTF8.encode(`${folder}/${path}`), entry })).sort(byName);
  for (const { name, entry } of sorted) {
    const length = entry.at.reduce((sum, [, , bytes]) => sum + bytes, 0);
    // A member in one range, as nearly every one is, is a view of its pack, read once; one split over packs
    // is read range by range, so that no more than its two last packs are held.
    const member = entry.at.length === 1 ? await rangeOf(entry.at[0], read) : null;
    const ranges = (from, to) => (member ? [member.subarray(from, to)] : rangesOf(entry.at, from, to, read));
    let plain = null;
    if (length >= GZIP_HEADER + GZIP_TRAILER) {
      const head = member ? member.subarray(0, GZIP_HEADER) : await bytesOf(entry.at, 0, GZIP_HEADER, read);
      if (isPlain(head)) {
        const tail = member ? member.subarray(length - GZIP_TRAILER) : await bytesOf(entry.at, length - GZIP_TRAILER, length, read);
        plain = trailerOf(tail, length, entry.bytes);
      }
    }
    if (plain) {
      for (const chunk of out.add(begin({ name, method: DEFLATED, ...plain }))) yield chunk;
      if (member) {
        for (const chunk of out.add(member.subarray(GZIP_HEADER, length - GZIP_TRAILER))) yield chunk;
      } else {
        for await (const piece of ranges(GZIP_HEADER, length - GZIP_TRAILER)) {
          for (const chunk of out.add(piece)) yield chunk;
        }
      }
      continue;
    }
    // Inflated twice rather than held: once for its CRC-32 and size, which its header goes before, then again
    // for its bytes.
    let crc = 0;
    let size = 0;
    for await (const piece of inflated(ranges(0, length))) {
      crc = crc32(piece, crc);
      size += piece.byteLength;
    }
    for (const chunk of out.add(begin({ name, method: STORED, crc, compressed: size, size }))) yield chunk;
    let again = 0;
    for await (const piece of inflated(ranges(0, length))) {
      again += piece.byteLength;
      for (const chunk of out.add(piece)) yield chunk;
    }
    if (again !== size) throw new Error("A member inflated to another size the second time.");
  }

  const start = offset;
  for (const file of written) {
    const record = centralHeader(file, limits);
    offset += record.byteLength;
    for (const chunk of out.add(record)) yield chunk;
  }
  for (const chunk of out.add(endRecords(written.length, offset - start, start, limits))) yield chunk;
  for (const chunk of out.rest()) yield chunk;
}

/** Whether a gzip member's first bytes are the plain form the command writes (RFC 1952: ID1, ID2, CM 8, and
 * FLG 0: no extra, no name, no comment, no header CRC), so that its deflate stream is its bytes but the 10 of
 * its header and the 8 of its trailer. */
function isPlain(head) {
  return head[0] === 0x1f && head[1] === 0x8b && head[2] === DEFLATED && head[3] === 0;
}

/** A plain member's CRC-32 and sizes, from its trailer: its CRC-32, and ISIZE, its size modulo 2^32, whose
 * entry's own size is taken where they agree (a file of 4 GiB or more). */
function trailerOf(tail, length, bytes) {
  const view = new DataView(tail.buffer, tail.byteOffset, GZIP_TRAILER);
  const isize = view.getUint32(4, true);
  return {
    crc: view.getUint32(0, true),
    compressed: length - GZIP_HEADER - GZIP_TRAILER,
    size: bytes % 2 ** 32 === isize ? bytes : isize,
  };
}

/** The bytes of one range, `[pack, offset, length]`: a view of its pack. */
async function rangeOf([pack, offset, length], read) {
  const bytes = await read(pack);
  if (offset + length > bytes.byteLength) throw new Error("A range runs past the end of its pack.");
  return bytes.subarray(offset, offset + length);
}

/** The bytes `from` to `to` of the member that `at`'s ranges hold, joined in order: pieces of its packs. */
async function* rangesOf(at, from, to, read) {
  let start = 0;
  for (const range of at) {
    const end = start + range[2];
    if (range[2] > 0 && end > from && start < to) {
      yield (await rangeOf(range, read)).subarray(Math.max(from, start) - start, Math.min(to, end) - start);
    }
    start = end;
    if (start >= to) return;
  }
}

async function bytesOf(at, from, to, read) {
  const bytes = new Uint8Array(to - from);
  let filled = 0;
  for await (const piece of rangesOf(at, from, to, read)) {
    bytes.set(piece, filled);
    filled += piece.byteLength;
  }
  return bytes;
}

/** Pieces of a gzip member, inflated as they come. */
async function* inflated(pieces) {
  const inflating = new DecompressionStream("gzip");
  const writer = inflating.writable.getWriter();
  const reader = inflating.readable.getReader();
  const fed = (async () => {
    try {
      for await (const piece of pieces) await writer.write(piece);
      await writer.close();
    } catch (error) {
      // The readable side fails with it, so that the read below does.
      await writer.abort(error).catch(() => {});
    }
  })();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      yield value;
    }
  } finally {
    await reader.cancel().catch(() => {});
    await fed;
  }
}

/** The zip's bytes gathered into chunks of ZIP_CHUNK bytes, each a copy of its own: no chunk is a view of a pack
 * the reader keeps, or of one it drops. */
class Chunks {
  #chunk = new Uint8Array(ZIP_CHUNK);
  #used = 0;

  /** `bytes` gathered: each chunk they fill, as it fills (one copied at a time, however long they are). */
  *add(bytes) {
    for (let at = 0; at < bytes.byteLength;) {
      const taken = Math.min(bytes.byteLength - at, ZIP_CHUNK - this.#used);
      this.#chunk.set(bytes.subarray(at, at + taken), this.#used);
      this.#used += taken;
      at += taken;
      if (this.#used === ZIP_CHUNK) {
        const filled = this.#chunk;
        this.#chunk = new Uint8Array(ZIP_CHUNK);
        this.#used = 0;
        yield filled;
      }
    }
  }

  /** What is gathered and not yet given, as the last chunk. */
  *rest() {
    if (this.#used > 0) yield this.#chunk.subarray(0, this.#used);
  }
}

/** Whether an entry needs Zip64 anywhere (its sizes in its local header and the central directory, its offset
 * there), and so says version 4.5. */
function zip64Of({ compressed, size, offset }, limits) {
  const sizes = compressed >= limits.size || size >= limits.size;
  return { sizes, any: sizes || offset >= limits.size };
}

/** A local file header (APPNOTE 4.3.7); with Zip64, an extra field of both sizes, uncompressed first (4.5.3). */
function localHeader(file, limits) {
  const { name, method, crc, compressed, size } = file;
  const zip64 = zip64Of(file, limits);
  const header = new Uint8Array(30 + name.byteLength + (zip64.sizes ? 20 : 0));
  const view = new DataView(header.buffer);
  view.setUint32(0, 0x04034b50, true);
  view.setUint16(4, zip64.any ? VERSION_ZIP64 : VERSION, true);
  view.setUint16(6, UTF8_NAMES, true);
  view.setUint16(8, method, true);
  view.setUint16(10, DOS_TIME, true);
  view.setUint16(12, DOS_DATE, true);
  view.setUint32(14, crc, true);
  view.setUint32(18, zip64.sizes ? 0xFFFFFFFF : compressed, true);
  view.setUint32(22, zip64.sizes ? 0xFFFFFFFF : size, true);
  view.setUint16(26, name.byteLength, true);
  view.setUint16(28, zip64.sizes ? 20 : 0, true);
  header.set(name, 30);
  if (zip64.sizes) {
    const at = 30 + name.byteLength;
    view.setUint16(at, 0x0001, true);
    view.setUint16(at + 2, 16, true);
    setUint64(view, at + 4, size);
    setUint64(view, at + 12, compressed);
  }
  return header;
}

/** A central directory header (APPNOTE 4.3.12); with Zip64, an extra field of each value its field cannot hold,
 * in the order uncompressed size, compressed size, offset (4.5.3). */
function centralHeader(file, limits) {
  const { name, method, crc, compressed, size, offset, folder } = file;
  const zip64 = zip64Of(file, limits);
  const big = [size, compressed, offset].map((value) => value >= limits.size);
  const values = [size, compressed, offset].filter((_, index) => big[index]);
  const extra = values.length ? 4 + 8 * values.length : 0;
  const record = new Uint8Array(46 + name.byteLength + extra);
  const view = new DataView(record.buffer);
  const version = zip64.any ? VERSION_ZIP64 : VERSION;
  view.setUint32(0, 0x02014b50, true);
  view.setUint16(4, MADE_ON_UNIX | version, true);
  view.setUint16(6, version, true);
  view.setUint16(8, UTF8_NAMES, true);
  view.setUint16(10, method, true);
  view.setUint16(12, DOS_TIME, true);
  view.setUint16(14, DOS_DATE, true);
  view.setUint32(16, crc, true);
  view.setUint32(20, big[1] ? 0xFFFFFFFF : compressed, true);
  view.setUint32(24, big[0] ? 0xFFFFFFFF : size, true);
  view.setUint16(28, name.byteLength, true);
  view.setUint16(30, extra, true);
  // A comment's length, the disk the file starts on and the internal attributes: none.
  view.setUint32(38, folder ? FOLDER_ATTRIBUTES : FILE_ATTRIBUTES, true);
  view.setUint32(42, big[2] ? 0xFFFFFFFF : offset, true);
  record.set(name, 46);
  if (extra) {
    const at = 46 + name.byteLength;
    view.setUint16(at, 0x0001, true);
    view.setUint16(at + 2, extra - 4, true);
    values.forEach((value, index) => setUint64(view, at + 4 + 8 * index, value));
  }
  return record;
}

/** The end of central directory record (APPNOTE 4.3.16), after the Zip64 end of central directory record and
 * its locator (4.3.14, 4.3.15) where the count, the directory's size or its offset needs them. */
function endRecords(count, size, offset, limits) {
  const zip64 = count >= limits.count || size >= limits.size || offset >= limits.size;
  const records = new Uint8Array((zip64 ? 56 + 20 : 0) + 22);
  const view = new DataView(records.buffer);
  let at = 0;
  if (zip64) {
    view.setUint32(0, 0x06064b50, true);
    setUint64(view, 4, 56 - 12);
    view.setUint16(12, MADE_ON_UNIX | VERSION_ZIP64, true);
    view.setUint16(14, VERSION_ZIP64, true);
    // This disk, and the disk the directory starts on: the first, 0.
    setUint64(view, 24, count);
    setUint64(view, 32, count);
    setUint64(view, 40, size);
    setUint64(view, 48, offset);
    view.setUint32(56, 0x07064b50, true);
    setUint64(view, 64, offset + size); // where the Zip64 record starts: right after the directory
    view.setUint32(72, 1, true); // one disk in all
    at = 76;
  }
  view.setUint32(at, 0x06054b50, true);
  view.setUint16(at + 8, count >= limits.count ? 0xFFFF : count, true);
  view.setUint16(at + 10, count >= limits.count ? 0xFFFF : count, true);
  view.setUint32(at + 12, size >= limits.size ? 0xFFFFFFFF : size, true);
  view.setUint32(at + 16, offset >= limits.size ? 0xFFFFFFFF : offset, true);
  return records;
}

function setUint64(view, at, value) {
  view.setUint32(at, value % 2 ** 32, true);
  view.setUint32(at + 4, Math.floor(value / 2 ** 32), true);
}

/** Entries in the order of their names' bytes. */
function byName(a, b) {
  const length = Math.min(a.name.byteLength, b.name.byteLength);
  for (let index = 0; index < length; index += 1) {
    if (a.name[index] !== b.name[index]) return a.name[index] - b.name[index];
  }
  return a.name.byteLength - b.name.byteLength;
}

// CRC-32 as zip and gzip compute it: the reflected polynomial 0xEDB88320.
const CRC_TABLE = Uint32Array.from({ length: 256 }, (_, byte) => {
  let crc = byte;
  for (let bit = 0; bit < 8; bit += 1) crc = crc & 1 ? 0xEDB88320 ^ (crc >>> 1) : crc >>> 1;
  return crc;
});

/** The CRC-32 of `bytes` following bytes whose CRC-32 is `crc`. */
function crc32(bytes, crc = 0) {
  let value = ~crc;
  for (let index = 0; index < bytes.byteLength; index += 1) value = CRC_TABLE[(value ^ bytes[index]) & 0xFF] ^ (value >>> 8);
  return ~value >>> 0;
}

// ---- storage --------------------------------------------------------------------------------------

/** Where a share lives in the bucket: under its name, which its id derives. */
async function placeOf(id) {
  const prefix = `s/${await nameOf(id)}/`;
  return { prefix, owner: `${prefix}owner`, manifest: `${prefix}manifest`, packs: `${prefix}p/` };
}

/** The share's owner, made by this write where it has none: put only if absent, and a create that loses
 * the race reads the one that won. Null where another write secret holds the share. */
async function claim(env, place, writeHash, deleteHash) {
  const customMetadata = { format: FORMAT, write: writeHash, delete: deleteHash };
  const made = await env.SHARES.put(place.owner, null, { onlyIf: new Headers({ "If-None-Match": "*" }), customMetadata });
  if (made) return { etag: made.etag, uploaded: made.uploaded, customMetadata };
  const owner = await env.SHARES.head(place.owner);
  return owner && ownedBy(owner, writeHash) ? owner : null;
}

function ownedBy(owner, writeHash) {
  return sameHex(owner.customMetadata?.write, writeHash);
}

/** The packs a stored manifest names, in its view and in its files. It opens (the service sealed what it
 * checked); where it would not, it names none. */
async function packsNamedBy(object, key) {
  const named = new Set();
  const plain = await open(key, new Uint8Array(await object.arrayBuffer()), MANIFEST_AAD);
  try {
    const manifest = JSON.parse(STRICT_UTF8.decode(plain));
    for (const map of [manifest.view, manifest.files]) {
      for (const entry of isObject(map) ? Object.values(map) : []) {
        for (const [pack] of entry.at) named.add(pack);
      }
    }
  } catch {
    // None kept: no page opens it either.
  }
  return named;
}

/** The lifecycle rule counts from an object's upload, and a commit keeps its owner and the packs it names
 * from earlier uploads: each of those the rule would delete before `until` is stored again, unchanged, by a
 * put conditional on its etag, so an object deleted meanwhile stays deleted. */
async function keepFromBackstop(env, place, owner, packs, until) {
  const taken = (object) => object.uploaded.getTime() + BACKSTOP_DAYS * DAY_MS <= until;
  if (taken(owner)) {
    await env.SHARES.put(place.owner, null, { onlyIf: { etagMatches: owner.etag }, customMetadata: owner.customMetadata });
  }
  const old = packs.filter(taken);
  for (let at = 0; at < old.length; at += AT_ONCE) {
    await Promise.all(old.slice(at, at + AT_ONCE).map(async ({ key }) => {
      const object = await env.SHARES.get(key);
      if (!object) return;
      await env.SHARES.put(key, await object.arrayBuffer(),
                           { onlyIf: { etagMatches: object.etag }, httpMetadata: object.httpMetadata });
    }));
  }
}

/** Every object of a share, deleted: its manifest first, so it is unreadable from the first call on, and
 * its owner last, so it is the owner's to delete until the end. */
async function deleteShare(env, place) {
  const rank = (key) => (key === place.manifest ? 0 : key === place.owner ? 2 : 1);
  const keys = (await listAll(env, place.prefix)).map((object) => object.key).sort((a, b) => rank(a) - rank(b));
  await removeKeys(env, keys);
}

/** Every object under `prefix`, page by page: R2 may answer fewer than a page holds, so `truncated` says
 * whether more follow. */
async function listAll(env, prefix) {
  const objects = [];
  for (let cursor; ;) {
    const page = await env.SHARES.list(cursor === undefined ? { prefix } : { prefix, cursor });
    objects.push(...page.objects);
    if (!page.truncated || !page.cursor) return objects;
    cursor = page.cursor;
  }
}

async function removeKeys(env, keys) {
  for (let at = 0; at < keys.length; at += DELETE_BATCH) await env.SHARES.delete(keys.slice(at, at + DELETE_BATCH));
}

/** A share manifest past its expiry, or with none kept, is no share. */
function expired(object, now) {
  const expires = Date.parse(object.customMetadata?.expires ?? "");
  return !(expires > now());
}

// ---- the share manifest ---------------------------------------------------------------------------

// A share manifest's members, every one required and no other taken: the view (the bundle a browser draws)
// and the files that made it (a model's code and what its build read, or a file document's file), each a
// map of paths to where their bytes lie, with the document's name, its entry and what made it.
const MEMBERS = ["format", "name", "entry", "made", "view", "files"];
const MEMBERS_TEXT = `${MEMBERS.slice(0, -1).join(", ")} and ${MEMBERS.at(-1)}`;
const MAPS = ["view", "files"];
const MAX_NAME_CHARACTERS = 200;
const MAX_MADE_MEMBERS = 32;
const MAX_MADE_CHARACTERS = 100;
const CONTROL = /\p{Cc}/u;

/** What a commit needs of its share manifest: how many files its view and its files list, and each pack
 * either names with the end of the furthest range read there. Or `{ problem }`, a sentence that says what
 * is not of its shape. */
function checkManifest(body) {
  let manifest;
  try {
    manifest = JSON.parse(STRICT_UTF8.decode(body));
  } catch {
    return { problem: "The body is not JSON in UTF-8." };
  }
  if (!isObject(manifest)) return { problem: `A share manifest is a JSON object of ${MEMBERS_TEXT}.` };
  const other = Object.keys(manifest).find((name) => !MEMBERS.includes(name));
  if (other !== undefined) return { problem: `A share manifest holds ${MEMBERS_TEXT}, and no ${quote(other)}.` };
  const absent = MEMBERS.find((name) => !Object.hasOwn(manifest, name));
  if (absent !== undefined) return { problem: `A share manifest holds ${MEMBERS_TEXT}: this one has no ${absent}.` };
  if (manifest.format !== FORMAT) return { problem: `A share manifest's format is "${FORMAT}".` };
  if (!isText(manifest.name, 1, MAX_NAME_CHARACTERS) || CONTROL.test(manifest.name)) {
    return { problem: `A share manifest's name is its document's: text of 1 to ${MAX_NAME_CHARACTERS} characters, no control character.` };
  }
  const made = madeProblem(manifest.made);
  if (made) return { problem: made };
  for (const map of MAPS) {
    if (!isObject(manifest[map])) return { problem: `A share manifest's ${map} is an object: each file by its path.` };
  }
  const count = Object.keys(manifest.view).length + Object.keys(manifest.files).length;
  if (count > MAX_FILES) return { problem: `A share manifest lists at most ${MAX_FILES} files, its view's and its files' together.` };
  if (!Object.hasOwn(manifest.view, "manifest.json")) {
    return { problem: "A share manifest's view lists the bundle's manifest.json." };
  }
  if (manifest.entry !== null && !(typeof manifest.entry === "string" && Object.hasOwn(manifest.files, manifest.entry))) {
    return { problem: "A share manifest's entry is the path in its files of the script that builds the model, or null." };
  }
  const packs = new Map();
  for (const map of MAPS) {
    for (const [path, entry] of Object.entries(manifest[map])) {
      const problem = pathProblem(path, map) ?? entryProblem(entry, packs);
      if (problem) return { problem: `${map}[${quote(path)}]: ${problem}.` };
    }
    const bare = bareHead(Object.keys(manifest[map]));
    if (bare !== null) return { problem: `${map}[${quote(bare)}]: ${CONTROL_PROBLEM}.` };
  }
  return { files: count, packs };
}

// The folders of a version control, whose settings name commands that an ordinary command run in the folder,
// or below it, runs (git's `core.fsmonitor`, which `git status` runs; a hook, an alias; Mercurial's hooks, and
// the like): a share's files, which an import writes into a folder, hold none. Each as `folded` spells it, and
// Windows' short names of them (`GIT~1`).
const VERSION_CONTROL = new Set([".git", ".hg", ".svn", ".bzr", "_darcs", ".jj", ".pijul", ".fslckout", "_fossil_"]);
const CONTROL_SHORT = /^(?:git|hg|svn|bzr|jj|pijul|fslcko)~[0-9]+$/;
// The code points HFS+ ignores in a name: `.g\u200cit` opens `.git` there.
const IGNORED = /[\u200c-\u200f\u202a-\u202e\u206a-\u206f\ufeff]/gu;
const CONTROL_PROBLEM = "a path is in no version control's folder (.git, .hg, .svn and the like) nor a repository's " +
  "bare form (HEAD beside objects and refs), whose settings would run commands where an import writes it";

/** A path's segment as the file systems that open it compare it: without the code points HFS+ ignores, before
 * an NTFS stream's `:`, composed, without the dots and spaces Windows drops from a name's end, in lower case. */
function folded(segment) {
  return segment.replace(IGNORED, "").split(":")[0].normalize("NFC").replace(/[. ]+$/, "").toLowerCase();
}

function isControl(segment) {
  const name = folded(segment);
  return VERSION_CONTROL.has(name) || CONTROL_SHORT.test(name);
}

/** The path of a `HEAD` among `paths` that sits beside an `objects` and a `refs` folder, which git takes for a
 * repository wherever it lies; or null. */
function bareHead(paths) {
  const folders = new Map();
  for (const path of paths) {
    const parts = path.split("/");
    parts.forEach((part, depth) => {
      const folder = parts.slice(0, depth).join("/");
      if (!folders.has(folder)) folders.set(folder, new Map());
      const names = folders.get(folder);
      const name = folded(part);
      if (!names.has(name)) names.set(name, depth === parts.length - 1 ? path : "");
    });
  }
  for (const names of folders.values()) {
    if (names.get("head") && names.has("objects") && names.has("refs")) return names.get("head");
  }
  return null;
}

/** What is wrong with `made`, or null: it is null (a file document's), or what built the model, each value text. */
function madeProblem(made) {
  const shape = `A share manifest's made is null, or what built the model: at most ${MAX_MADE_MEMBERS} members, ` +
    `each name and value text of at most ${MAX_MADE_CHARACTERS} characters`;
  if (made === null) return null;
  if (!isObject(made) || Object.keys(made).length > MAX_MADE_MEMBERS) return `${shape}.`;
  const bad = Object.entries(made).find(([name, value]) => !isText(name, 0, MAX_MADE_CHARACTERS)
                                                          || !isText(value, 0, MAX_MADE_CHARACTERS));
  return bad ? `${shape}; made[${quote(bad[0])}] is not.` : null;
}

/** Whether a value is text (a string with no lone surrogate) of `least` to `most` characters. */
function isText(value, least, most) {
  if (typeof value !== "string" || !value.isWellFormed() || value.length > 2 * most) return false;
  const characters = [...value].length;
  return characters >= least && characters <= most;
}

function pathProblem(path, map) {
  if (!path.isWellFormed()) return "a path is text";
  if (UTF8.encode(path).byteLength > MAX_PATH_BYTES) return `a path is at most ${MAX_PATH_BYTES} bytes`;
  if (path.startsWith("/") || path.includes("\\") || /^[A-Za-z]:/.test(path)) return "a path is relative and / separated";
  if (path.split("/").some((segment) => segment === "" || segment === "." || segment === "..")) {
    return "a path has no empty, . or .. segment";
  }
  if (path.split("/").some(isControl)) return CONTROL_PROBLEM;
  // The bundle's own thumbnail may show an earlier version of the document; a file of that name the build
  // read is one of the files.
  if (map === "view" && path === "thumbnail.png") return "the bundle's thumbnail.png is left out of a share";
  return null;
}

function entryProblem(entry, packs) {
  if (!isObject(entry)) return "a file is an object: its sha256, bytes and at";
  const other = Object.keys(entry).find((name) => name !== "sha256" && name !== "bytes" && name !== "at");
  if (other !== undefined) return `a file holds sha256, bytes and at, and no ${quote(other)}`;
  if (typeof entry.sha256 !== "string" || !HEX_SHA256.test(entry.sha256)) return "sha256 is 64 lowercase hex characters";
  if (!isWhole(entry.bytes)) return "bytes is a whole number";
  if (!Array.isArray(entry.at) || entry.at.length === 0) return "at is one or more [pack id, offset, length]";
  for (const range of entry.at) {
    if (!Array.isArray(range) || range.length !== 3 || typeof range[0] !== "string" || !HEX_SHA256.test(range[0])
        || !isWhole(range[1]) || !isWhole(range[2])) {
      return "each of at is [pack id, offset, length]: 64 lowercase hex characters, then two whole numbers";
    }
    const [pack, offset, size] = range;
    packs.set(pack, Math.max(packs.get(pack) ?? 0, offset + size));
  }
  return null;
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isWhole(value) {
  return Number.isSafeInteger(value) && value >= 0;
}

/** A name or a path, as a hint quotes it: in JSON, and cut short where it is long. */
function quote(text) {
  return JSON.stringify(text.length > 80 ? `${text.slice(0, 80)}...` : text);
}

// ---- names and secrets ----------------------------------------------------------------------------

/** 32 bytes the id derives for `info` ("key" or "name"): HKDF-SHA256, the id's text as the input keying
 * material and the format's as the salt. */
export async function derive(id, info) {
  const material = await crypto.subtle.importKey("raw", UTF8.encode(id), "HKDF", false, ["deriveBits"]);
  const bits = await crypto.subtle.deriveBits(
    { name: "HKDF", hash: "SHA-256", salt: UTF8.encode(FORMAT), info: UTF8.encode(info) }, material, 256);
  return new Uint8Array(bits);
}

/** The name a share is stored under (`s/<name>/`): its id's `name`, 64 lowercase hex characters. */
export async function nameOf(id) {
  return hex(await derive(id, "name"));
}

/** The share's key, imported non-extractable: it goes out of scope with the request and is never stored. */
async function keyOf(id) {
  return crypto.subtle.importKey("raw", await derive(id, "key"), { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}

/** `IV || AES-256-GCM(key, IV, plaintext, aad)`, the tag at the end. The IV is 12 fresh random bytes; the
 * tests give their own, for the protocol's test vectors. */
export async function seal(key, plaintext, aad, iv = crypto.getRandomValues(new Uint8Array(IV_BYTES))) {
  const params = { name: "AES-GCM", iv, additionalData: UTF8.encode(aad) };
  const sealed = new Uint8Array(await crypto.subtle.encrypt(params, key, plaintext));
  const stored = new Uint8Array(IV_BYTES + sealed.byteLength);
  stored.set(iv, 0);
  stored.set(sealed, IV_BYTES);
  return stored;
}

/** What `seal` sealed, or null where it does not open. */
async function open(key, stored, aad) {
  try {
    const params = { name: "AES-GCM", iv: stored.subarray(0, IV_BYTES), additionalData: UTF8.encode(aad) };
    return new Uint8Array(await crypto.subtle.decrypt(params, key, stored.subarray(IV_BYTES)));
  } catch {
    return null;
  }
}

/** The lowercase hex SHA-256 of bytes, or of a secret's text as it travels (its 43 base64url characters). */
export async function sha256Hex(data) {
  return hex(new Uint8Array(await crypto.subtle.digest("SHA-256", typeof data === "string" ? UTF8.encode(data) : data)));
}

function hex(bytes) {
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** Whether a kept hash is the one given, in time that does not depend on where they differ. */
function sameHex(kept, given) {
  if (typeof kept !== "string" || kept.length !== given.length) return false;
  let difference = 0;
  for (let index = 0; index < kept.length; index += 1) difference |= kept.charCodeAt(index) ^ given.charCodeAt(index);
  return difference === 0;
}

// ---- a request's parts ----------------------------------------------------------------------------

function settingsOf(env) {
  return {
    maxPackBytes: positive(env.MAX_PACK_BYTES, DEFAULTS.MAX_PACK_BYTES),
    maxManifestBytes: positive(env.MAX_MANIFEST_BYTES, DEFAULTS.MAX_MANIFEST_BYTES),
    maxShareBytes: positive(env.MAX_SHARE_BYTES, DEFAULTS.MAX_SHARE_BYTES),
    expiryDays: positive(env.EXPIRY_DAYS, DEFAULTS.EXPIRY_DAYS),
  };
}

function positive(value, fallback) {
  const number = Number(value);
  return value !== undefined && value !== "" && Number.isFinite(number) && number > 0 ? number : fallback;
}

/** The client's address, which Cloudflare sets on every request it passes to the Worker. */
export function clientAddress(request) {
  return request.headers.get("CF-Connecting-IP") || "unknown";
}

async function allowed(limiter, request) {
  const { success } = await limiter.limit({ key: clientAddress(request) });
  return success;
}

/** The secret a request is made with (`Authorization: Bearer`), or the refusal of one without it. */
function bearerOf(request, which) {
  const match = BEARER.exec(request.headers.get("Authorization") ?? "");
  if (!match) {
    return { refusal: refuse(401, "unauthorized", `Send Authorization: Bearer <${which}>.`, { "WWW-Authenticate": "Bearer" }) };
  }
  if (!SECRET.test(match[1])) return { refusal: refuse(400, "bad_secret", "A secret is 43 characters of base64url.") };
  return { secret: match[1] };
}

/** A write's write secret and its delete secret's hash, or the refusal of a write without them. */
function writerOf(request) {
  const bearer = bearerOf(request, "write secret");
  if (bearer.refusal) return bearer;
  const deleteHash = request.headers.get("Cad-Delete-Hash") ?? "";
  if (!HEX_SHA256.test(deleteHash)) {
    return { refusal: refuse(400, "bad_delete_hash", "Cad-Delete-Hash is the lowercase hex SHA-256 of the delete secret.") };
  }
  return { secret: bearer.secret, deleteHash };
}

function lengthOf(request) {
  const length = request.headers.get("Content-Length");
  return length !== null && /^\d+$/.test(length) ? Number(length) : null;
}

/** The body, or null where it runs past `limit` (whatever Content-Length claimed). It is read into
 * one buffer of the length declared, so a body near the cap is held once, not twice. */
async function readAtMost(request, declared, limit) {
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  let body = new Uint8Array(declared);
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (total + value.byteLength > limit) {
      await reader.cancel();
      return null;
    }
    if (total + value.byteLength > body.byteLength) {
      const grown = new Uint8Array(total + value.byteLength);
      grown.set(body.subarray(0, total));
      body = grown;
    }
    body.set(value, total);
    total += value.byteLength;
  }
  return total === body.byteLength ? body : body.subarray(0, total);
}

// ---- the pages and the viewer's files -------------------------------------------------------------

async function asset(request, env) {
  // Asked as a plain GET, whatever came: an HTML answer's policy hashes the scripts its body holds (a HEAD
  // has none, nor has a 304 to a conditional request).
  const response = await env.ASSETS.fetch(new Request(request.url, { method: "GET" }));
  if (response.status === 404) return refuse(404, "not_found", "No such page or file.");
  if (isHtml(response)) return page(request, response);
  const passed = new Response(request.method === "HEAD" ? null : response.body, response);
  passed.headers.set("X-Content-Type-Options", "nosniff");
  return passed;
}

async function page(request, response) {
  const html = await response.text();
  const headers = new Headers(response.headers);
  headers.delete("Content-Length");
  headers.delete("ETag");
  headers.set("Content-Type", "text/html; charset=utf-8");
  headers.set("Cache-Control", "no-cache");
  for (const [name, value] of Object.entries(await pageHeaders(html))) headers.set(name, value);
  return new Response(request.method === "HEAD" ? null : html, { status: response.status, headers });
}

/** The security headers of an HTML answer, its inline scripts allowed by their hashes. */
export async function pageHeaders(html) {
  const policy = structuredClone(CSP);
  for (const script of inlineScripts(html)) policy["script-src"].push(`'sha256-${await sha256Base64(script)}'`);
  return {
    "Content-Security-Policy": Object.entries(policy).map(([name, values]) => `${name} ${values.join(" ")}`).join("; "),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
  };
}

function inlineScripts(html) {
  const scripts = [];
  for (const [, attributes, text] of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script\s*>/gi)) {
    if (!/\bsrc\s*=/i.test(attributes) && text.length > 0) scripts.push(text);
  }
  return scripts;
}

async function sha256Base64(text) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", UTF8.encode(text)));
  return btoa(String.fromCharCode(...digest));
}

function isHtml(response) {
  return /^text\/html\b/i.test(response.headers.get("Content-Type") ?? "");
}

function isRead(request) {
  return request.method === "GET" || request.method === "HEAD";
}

// ---- answers ---------------------------------------------------------------------------------------

function json(status, body, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extra,
    },
  });
}

function refuse(status, error, hint, extra) {
  return json(status, { error, hint }, extra);
}

function gone() {
  return refuse(404, "not_found", "No share has this id: it expired, was deleted, or never existed.");
}

function forbidden() {
  return refuse(403, "forbidden", "Another write secret made this share. Make a new share.");
}

function lengthRequired() {
  return refuse(411, "length_required", "Send Content-Length.");
}

function tooLarge(hint) {
  return refuse(413, "too_large", hint);
}

function limited(what) {
  return refuse(429, "rate_limited", `Too many ${what} from this address. Wait a minute.`,
                { "Retry-After": String(RETRY_AFTER_SECONDS) });
}

function notAllowed(allow) {
  return refuse(405, "method_not_allowed", `This path takes ${allow}.`, { Allow: allow });
}
