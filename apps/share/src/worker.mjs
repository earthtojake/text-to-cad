// The share service: a Cloudflare Worker over an R2 bucket (SHARES), the viewer's static assets
// (ASSETS) and a rate limiter (LIMITER). Its API and pages are README.md's; this file is the whole of
// the service, and `serve.mjs` runs this same module locally over Node's http.
//
// Nothing here logs a header or a body. An upload carries the share's key (Cad-Share-Key) and its
// write secret (Authorization); a delete carries a secret. They pass through this code, are used
// and dropped, and never reach a log line, a stored field, an error message or a response.

export const FORMAT = "cad-share/1";
export const HOME = "https://www.texttocad.dev";
export const DEFAULT_MAX_SHARE_BYTES = 25 * 1024 * 1024;
export const DEFAULT_EXPIRY_DAYS = 7;
// The limiter counts per minute (wrangler.jsonc: `simple.period`), so a refused client waits that.
export const RETRY_AFTER_SECONDS = 60;

const ID = /^[A-Za-z0-9_-]{22}$/;
const SECRET = /^[A-Za-z0-9_-]{43}$/;
const HEX_SHA256 = /^[0-9a-f]{64}$/;
const BEARER = /^Bearer ([^\s]+)$/;
const SHARE_PATH = /^\/v1\/shares\/([^/]*)$/;
const IV_BYTES = 12;
const DAY_MS = 24 * 60 * 60 * 1000;
// A create that loses its put-if-absent to another client's, or a replace whose share changed under
// it, looks again: the other upload is then the share that exists, and is judged as one.
const PUT_ATTEMPTS = 3;

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
  const url = new URL(request.url);
  const path = url.pathname;
  if (path === "/v1" || path.startsWith("/v1/")) {
    const match = SHARE_PATH.exec(path);
    if (!match) return refuse(404, "not_found", "The API has one route: /v1/shares/<id>.");
    const id = match[1];
    if (!ID.test(id)) return refuse(400, "bad_id", "A share id is 22 characters of base64url.");
    const settings = settingsOf(env);
    switch (request.method) {
      case "PUT": return upload(request, env, id, settings, now);
      case "GET": case "HEAD": return read(request, env, id, now);
      case "DELETE": return remove(request, env, id, now);
      default: return notAllowed("PUT, GET, HEAD, DELETE");
    }
  }
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

async function upload(request, env, id, settings, now) {
  const secret = bearerOf(request);
  if (!secret) return refuse(401, "unauthorized", "Send Authorization: Bearer <write secret>.",
                             { "WWW-Authenticate": "Bearer" });
  const keyBytes = keyOf(request.headers.get("Cad-Share-Key"));
  if (!keyBytes) return refuse(400, "bad_key", "Cad-Share-Key is 32 bytes in base64url without padding.");
  const deleteHash = request.headers.get("Cad-Delete-Hash") ?? "";
  if (!HEX_SHA256.test(deleteHash)) {
    return refuse(400, "bad_delete_hash", "Cad-Delete-Hash is the lowercase hex SHA-256 of the delete secret.");
  }
  const length = request.headers.get("Content-Length");
  if (length === null || !/^\d+$/.test(length)) return refuse(411, "length_required", "Send Content-Length.");
  if (Number(length) > settings.maxBytes) return tooLarge(settings);
  if (!(await allowed(request, env))) return limited();

  const body = await readAtMost(request, settings.maxBytes);
  if (body === null) return tooLarge(settings);
  if (body.byteLength < 2 || body[0] !== 0x1f || body[1] !== 0x8b) {
    return refuse(400, "not_gzip", "The body is the share's archive, gzip-compressed.");
  }

  const writeHash = await sha256Hex(secret);
  const expires = new Date(now() + settings.expiryDays * DAY_MS).toISOString();
  let stored = null;
  for (let attempt = 0; attempt < PUT_ATTEMPTS; attempt += 1) {
    const existing = await env.SHARES.head(id);
    const live = existing && !expired(existing, now);
    if (live && !sameHex(existing.customMetadata?.write, writeHash)) {
      return refuse(403, "forbidden", "Another write secret made this share. Make a new share.");
    }
    // Absent: put only if still absent. Present (live, or expired and so free): only if unchanged.
    const onlyIf = existing ? { etagMatches: existing.etag } : new Headers({ "If-None-Match": "*" });
    stored ??= await encrypt(keyBytes, body);
    const put = await env.SHARES.put(id, stored, {
      onlyIf,
      httpMetadata: { contentType: "application/octet-stream" },
      customMetadata: { format: FORMAT, write: writeHash, delete: deleteHash, expires },
    });
    if (put) return json(live ? 200 : 201, { id, expires, bytes: stored.byteLength });
  }
  return refuse(409, "conflict", "Another upload to this share happened at the same moment. Try again.");
}

async function read(request, env, id, now) {
  const object = request.method === "HEAD" ? await env.SHARES.head(id) : await env.SHARES.get(id);
  if (!object || expired(object, now)) {
    if (object) await env.SHARES.delete(id);
    return missing();
  }
  const headers = {
    "Content-Type": "application/octet-stream",
    "Content-Length": String(object.size),
    "Cache-Control": "no-store",
    "Cad-Share-Expires": object.customMetadata.expires,
    "X-Content-Type-Options": "nosniff",
  };
  return new Response(request.method === "HEAD" ? null : object.body, { status: 200, headers });
}

async function remove(request, env, id, now) {
  const secret = bearerOf(request);
  if (!secret) return refuse(401, "unauthorized", "Send Authorization: Bearer <delete secret>.",
                             { "WWW-Authenticate": "Bearer" });
  if (!(await allowed(request, env))) return limited();
  const existing = await env.SHARES.head(id);
  if (!existing || expired(existing, now)) {
    if (existing) await env.SHARES.delete(id);
    return missing();
  }
  const hash = await sha256Hex(secret);
  const kept = existing.customMetadata ?? {};
  if (!sameHex(kept.delete, hash) && !sameHex(kept.write, hash)) {
    return refuse(403, "forbidden", "This secret is neither the share's delete secret nor its write secret.");
  }
  await env.SHARES.delete(id);
  return new Response(null, { status: 204, headers: { "Cache-Control": "no-store" } });
}

function settingsOf(env) {
  return {
    maxBytes: positive(env.MAX_SHARE_BYTES, DEFAULT_MAX_SHARE_BYTES),
    expiryDays: positive(env.EXPIRY_DAYS, DEFAULT_EXPIRY_DAYS),
  };
}

function positive(value, fallback) {
  const number = Number(value);
  return value !== undefined && value !== "" && Number.isFinite(number) && number > 0 ? number : fallback;
}

/** A share past its expiry, or with none kept, is no share. */
function expired(object, now) {
  const expires = Date.parse(object.customMetadata?.expires ?? "");
  return !(expires > now());
}

/** The client's address, which Cloudflare sets on every request it passes to the Worker. */
export function clientAddress(request) {
  return request.headers.get("CF-Connecting-IP") || "unknown";
}

async function allowed(request, env) {
  const { success } = await env.LIMITER.limit({ key: clientAddress(request) });
  return success;
}

function bearerOf(request) {
  const match = BEARER.exec(request.headers.get("Authorization") ?? "");
  return match && SECRET.test(match[1]) ? match[1] : null;
}

function keyOf(header) {
  if (!header || !SECRET.test(header)) return null;
  const bytes = fromBase64Url(header);
  return bytes.byteLength === 32 ? bytes : null;
}

/** The body, or null where it runs past `limit` (whatever Content-Length claimed). */
async function readAtMost(request, limit) {
  if (!request.body) return new Uint8Array(0);
  const reader = request.body.getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > limit) {
      await reader.cancel();
      return null;
    }
    chunks.push(value);
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    body.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return body;
}

/** `IV || ciphertext-and-tag`, AES-256-GCM under the upload's key and a fresh random IV. The key is
 * imported as non-extractable and goes out of scope with this call: it is never stored. */
async function encrypt(keyBytes, plaintext) {
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(IV_BYTES));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, plaintext));
  const stored = new Uint8Array(IV_BYTES + sealed.byteLength);
  stored.set(iv, 0);
  stored.set(sealed, IV_BYTES);
  return stored;
}

/** The lowercase hex SHA-256 of a secret's text as it travels (its 43 base64url characters). */
export async function sha256Hex(text) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function sameHex(kept, given) {
  if (typeof kept !== "string" || kept.length !== given.length) return false;
  let difference = 0;
  for (let index = 0; index < kept.length; index += 1) difference |= kept.charCodeAt(index) ^ given.charCodeAt(index);
  return difference === 0;
}

function fromBase64Url(text) {
  const base64 = text.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (text.length % 4)) % 4);
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

// ---- the pages and the viewer's files -------------------------------------------------------------

async function asset(request, env) {
  // A HEAD is asked as a GET, so an HTML answer's policy hashes the scripts its body holds.
  const asked = request.method === "HEAD" ? new Request(request, { method: "GET" }) : request;
  const response = await env.ASSETS.fetch(asked);
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
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)));
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

function missing() {
  return refuse(404, "not_found", "No share has this id: it expired, was deleted, or never existed.");
}

function tooLarge(settings) {
  return refuse(413, "too_large", `A share is at most ${settings.maxBytes} bytes.`);
}

function limited() {
  return refuse(429, "rate_limited", "Too many uploads or deletes from this address. Wait a minute.",
                { "Retry-After": String(RETRY_AFTER_SECONDS) });
}

function notAllowed(allow) {
  return refuse(405, "method_not_allowed", `This path takes ${allow}.`, { Allow: allow });
}
