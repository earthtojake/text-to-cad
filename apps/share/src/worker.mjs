// The share service: a Cloudflare Worker over an R2 bucket (SHARES), the viewer's static assets (ASSETS)
// and two rate limiters (LIMITER for commits and deletes, LIMITER_PACKS for packs). Its API, storage and
// pages are README.md's; this file is the whole of the service, and `serve.mjs` runs this same module
// locally over Node's http.
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
/** The most files a share manifest lists. */
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
  if (!(await allowed(env.LIMITER_PACKS, request))) return limited("pack uploads");

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

/** The packs a stored manifest names. It opens (the service sealed what it checked); where it would not,
 * it names none. */
async function packsNamedBy(object, key) {
  const named = new Set();
  const plain = await open(key, new Uint8Array(await object.arrayBuffer()), MANIFEST_AAD);
  try {
    for (const entry of Object.values(JSON.parse(STRICT_UTF8.decode(plain)).files)) {
      for (const [pack] of entry.at) named.add(pack);
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

/** What a commit needs of its share manifest: how many files it lists, and each pack it names with the end
 * of the furthest range it reads there. Or `{ problem }`, a sentence that says what is not of its shape. */
function checkManifest(body) {
  let manifest;
  try {
    manifest = JSON.parse(STRICT_UTF8.decode(body));
  } catch {
    return { problem: "The body is not JSON in UTF-8." };
  }
  if (!isObject(manifest)) return { problem: "A share manifest is a JSON object, its format and its files." };
  const other = Object.keys(manifest).find((name) => name !== "format" && name !== "files");
  if (other !== undefined) return { problem: `A share manifest holds format and files, and no ${quote(other)}.` };
  if (manifest.format !== FORMAT) return { problem: `A share manifest's format is "${FORMAT}".` };
  if (!isObject(manifest.files)) return { problem: "A share manifest's files are an object: each file by its path." };
  const paths = Object.keys(manifest.files);
  if (paths.length > MAX_FILES) return { problem: `A share manifest lists at most ${MAX_FILES} files.` };
  if (!Object.hasOwn(manifest.files, "manifest.json")) {
    return { problem: "A share manifest lists the bundle's manifest.json." };
  }
  const packs = new Map();
  for (const path of paths) {
    const problem = pathProblem(path) ?? entryProblem(manifest.files[path], packs);
    if (problem) return { problem: `files[${quote(path)}]: ${problem}.` };
  }
  return { files: paths.length, packs };
}

function pathProblem(path) {
  if (!path.isWellFormed()) return "a path is text";
  if (UTF8.encode(path).byteLength > MAX_PATH_BYTES) return `a path is at most ${MAX_PATH_BYTES} bytes`;
  if (path.startsWith("/") || path.includes("\\") || /^[A-Za-z]:/.test(path)) return "a path is relative and / separated";
  if (path.split("/").some((segment) => segment === "" || segment === "." || segment === "..")) {
    return "a path has no empty, . or .. segment";
  }
  if (path === "thumbnail.png") return "the bundle's thumbnail.png is left out of a share";
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

/** What `seal` sealed, or empty bytes where it does not open. */
async function open(key, stored, aad) {
  try {
    const params = { name: "AES-GCM", iv: stored.subarray(0, IV_BYTES), additionalData: UTF8.encode(aad) };
    return new Uint8Array(await crypto.subtle.decrypt(params, key, stored.subarray(IV_BYTES)));
  } catch {
    return new Uint8Array(0);
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
