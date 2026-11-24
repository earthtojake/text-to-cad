// The Worker's platform, locally: stand-ins for what Cloudflare gives it (the R2 bucket, the static
// assets, the rate limiter, the client's address and the asset-first routing of wrangler.jsonc), and
// a Node http server that runs the real Worker module over them. `serve.mjs` is its command; the
// tests use it directly. Each stand-in does what the Worker asks of its original, as Cloudflare's
// documentation describes it (README.md, "Cloudflare, as relied on"), and no more.
//
// Like the Worker, nothing here logs a header or a body.

import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, rename, rm, stat, writeFile } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, resolve, sep } from "node:path";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

import worker from "./worker.mjs";

export const APP_ROOT = fileURLToPath(new URL("..", import.meta.url));

// ---- the configuration ------------------------------------------------------------------------------

/** wrangler.jsonc, read as Wrangler reads it: JSON with comments. */
export async function readConfig(file = join(APP_ROOT, "wrangler.jsonc")) {
  return JSON.parse(stripComments(await readFile(file, "utf8")));
}

function stripComments(text) {
  let out = "";
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"') {
      let end = index + 1;
      while (end < text.length && text[end] !== '"') end += text[end] === "\\" ? 2 : 1;
      out += text.slice(index, end + 1);
      index = end;
    } else if (character === "/" && text[index + 1] === "/") {
      while (index < text.length && text[index] !== "\n") index += 1;
      out += "\n";
    } else if (character === "/" && text[index + 1] === "*") {
      index = text.indexOf("*/", index + 2) + 1;
    } else {
      out += character;
    }
  }
  return out;
}

/** `assets.run_worker_first`: `true`, `false`, or patterns where `*` matches deeply and a `!`
 * pattern excludes, ahead of every other. */
export function runsWorkerFirst(setting, pathname) {
  if (typeof setting === "boolean") return setting;
  if (!Array.isArray(setting)) return false;
  const matches = (pattern) => new RegExp(`^${pattern.split("*").map(escapeRegExp).join(".*")}$`).test(pathname);
  if (setting.some((pattern) => pattern.startsWith("!") && matches(pattern.slice(1)))) return false;
  return setting.some((pattern) => !pattern.startsWith("!") && matches(pattern));
}

function escapeRegExp(text) {
  return text.replace(/[.+?^${}()|[\]\\]/g, "\\$&");
}

// ---- R2 -------------------------------------------------------------------------------------------

/** An R2 bucket in memory, or in files under `directory`: `put` (with `onlyIf`, `customMetadata`,
 * `httpMetadata`), `get`, `head` and `delete`. Each operation is atomic, as R2's are: they run one
 * at a time. */
export class LocalBucket {
  #objects = new Map();
  #queue = Promise.resolve();

  constructor(directory = null) {
    this.directory = directory ? resolve(directory) : null;
  }

  head(key) {
    return this.#serial(async () => {
      const record = await this.#load(key);
      return record ? objectOf(key, record) : null;
    });
  }

  get(key) {
    return this.#serial(async () => {
      const record = await this.#load(key);
      return record ? bodyOf(key, record) : null;
    });
  }

  put(key, value, options = {}) {
    return this.#serial(async () => {
      const bytes = await bytesOf(value);
      const existing = await this.#load(key);
      if (!meets(options.onlyIf, existing)) return null;
      const record = {
        bytes,
        etag: createHash("md5").update(bytes).digest("hex"),
        uploaded: new Date().toISOString(),
        customMetadata: { ...(options.customMetadata ?? {}) },
        httpMetadata: httpMetadataOf(options.httpMetadata),
      };
      await this.#store(key, record);
      return objectOf(key, record);
    });
  }

  delete(keys) {
    return this.#serial(async () => {
      for (const key of Array.isArray(keys) ? keys : [keys]) await this.#drop(key);
    });
  }

  /** Every key held, for tests that look at what was kept. */
  keys() {
    return this.#serial(async () => [...this.#objects.keys()]);
  }

  #serial(operation) {
    const result = this.#queue.then(operation);
    this.#queue = result.catch(() => {});
    return result;
  }

  async #load(key) {
    if (this.#objects.has(key)) return this.#objects.get(key);
    if (!this.directory) return null;
    const [meta, bytes] = await Promise.all([
      readFile(this.#file(key, "json"), "utf8").catch(() => null),
      readFile(this.#file(key, "bin")).catch(() => null),
    ]);
    if (meta === null || bytes === null) return null;
    const record = { ...JSON.parse(meta), bytes: new Uint8Array(bytes) };
    this.#objects.set(key, record);
    return record;
  }

  async #store(key, record) {
    this.#objects.set(key, record);
    if (!this.directory) return;
    await mkdir(this.directory, { recursive: true });
    const { bytes, ...meta } = record;
    await writeAtomically(this.#file(key, "bin"), bytes);
    await writeAtomically(this.#file(key, "json"), JSON.stringify(meta));
  }

  async #drop(key) {
    this.#objects.delete(key);
    if (!this.directory) return;
    await rm(this.#file(key, "json"), { force: true });
    await rm(this.#file(key, "bin"), { force: true });
  }

  #file(key, suffix) {
    return join(this.directory, `${encodeURIComponent(key)}.${suffix}`);
  }
}

async function writeAtomically(file, data) {
  const temporary = `${file}.${randomUUID()}.tmp`;
  await writeFile(temporary, data);
  await rename(temporary, file);
}

async function bytesOf(value) {
  if (value === null || value === undefined) return new Uint8Array(0);
  if (typeof value === "string") return new TextEncoder().encode(value);
  if (value instanceof ArrayBuffer) return new Uint8Array(value.slice(0));
  if (ArrayBuffer.isView(value)) return new Uint8Array(value.buffer.slice(value.byteOffset, value.byteOffset + value.byteLength));
  if (value instanceof Blob) return new Uint8Array(await value.arrayBuffer());
  if (value instanceof ReadableStream) return new Uint8Array(await new Response(value).arrayBuffer());
  throw new TypeError("put: unsupported value");
}

function httpMetadataOf(metadata) {
  if (!metadata) return {};
  if (metadata instanceof Headers) {
    const named = { "content-type": "contentType", "content-language": "contentLanguage",
                    "content-disposition": "contentDisposition", "content-encoding": "contentEncoding",
                    "cache-control": "cacheControl" };
    return Object.fromEntries([...metadata].filter(([name]) => named[name]).map(([name, value]) => [named[name], value]));
  }
  return { ...metadata };
}

/** Whether a put's `onlyIf` holds: an R2Conditional, or a Headers of conditional headers. */
function meets(onlyIf, existing) {
  if (!onlyIf) return true;
  const etag = existing?.etag ?? null;
  const uploaded = existing ? Date.parse(existing.uploaded) : null;
  if (onlyIf instanceof Headers) {
    const match = onlyIf.get("If-Match");
    const noneMatch = onlyIf.get("If-None-Match");
    const since = onlyIf.get("If-Modified-Since");
    const unmodified = onlyIf.get("If-Unmodified-Since");
    if (match !== null && !(existing && etagListHas(match, etag))) return false;
    if (noneMatch !== null && existing && etagListHas(noneMatch, etag)) return false;
    if (unmodified !== null && existing && uploaded > Date.parse(unmodified)) return false;
    if (since !== null && existing && !(uploaded > Date.parse(since))) return false;
    return true;
  }
  const { etagMatches, etagDoesNotMatch, uploadedBefore, uploadedAfter } = onlyIf;
  if (etagMatches !== undefined && !(existing && etagListHas(etagMatches, etag))) return false;
  if (etagDoesNotMatch !== undefined && existing && etagListHas(etagDoesNotMatch, etag)) return false;
  if (uploadedBefore !== undefined && existing && !(uploaded < uploadedBefore.getTime())) return false;
  if (uploadedAfter !== undefined && existing && !(uploaded > uploadedAfter.getTime())) return false;
  return true;
}

function etagListHas(list, etag) {
  return String(list).split(",").map((entry) => entry.trim().replace(/^W\//, "").replace(/^"|"$/g, ""))
    .some((entry) => entry === "*" || (etag !== null && entry === etag));
}

function objectOf(key, record) {
  return {
    key,
    size: record.bytes.byteLength,
    etag: record.etag,
    httpEtag: `"${record.etag}"`,
    uploaded: new Date(record.uploaded),
    customMetadata: { ...record.customMetadata },
    httpMetadata: { ...record.httpMetadata },
  };
}

function bodyOf(key, record) {
  const bytes = record.bytes;
  let used = false;
  const take = () => {
    if (used) throw new TypeError("The body has already been used.");
    used = true;
    return bytes.slice();
  };
  let stream = null;
  return {
    ...objectOf(key, record),
    get bodyUsed() { return used; },
    // One stream, which takes the bytes when it is first read.
    get body() {
      stream ??= new ReadableStream({ pull(controller) { controller.enqueue(take()); controller.close(); } });
      return stream;
    },
    async arrayBuffer() { return take().buffer; },
    async text() { return new TextDecoder().decode(take()); },
    async json() { return JSON.parse(new TextDecoder().decode(take())); },
    async blob() { return new Blob([take()]); },
  };
}

// ---- static assets --------------------------------------------------------------------------------

const TYPES = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".map": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
  ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
  ".ico": "image/x-icon", ".wasm": "application/wasm", ".woff": "font/woff", ".woff2": "font/woff2",
  ".ttf": "font/ttf", ".otf": "font/otf", ".webmanifest": "application/manifest+json",
};

/** The ASSETS binding over the files under `directory`, as wrangler.jsonc configures it
 * (`html_handling: "none"`, `not_found_handling: "none"`): a path answers the file at exactly that
 * path, and anything else is a 404. Only the URL's path is read. */
export function localAssets(directory) {
  const root = resolve(directory);
  const fileOf = async (pathname) => {
    let decoded;
    try { decoded = decodeURIComponent(pathname); } catch { return null; }
    if (decoded.includes("\0") || decoded.split("/").includes("..")) return null;
    const file = resolve(root, `.${decoded}`);
    if (file !== root && !file.startsWith(root + sep)) return null;
    const found = await stat(file).catch(() => null);
    return found?.isFile() ? { file, size: found.size, modified: found.mtimeMs } : null;
  };
  return {
    async has(pathname) {
      return (await fileOf(pathname)) !== null;
    },
    async fetch(input) {
      const request = input instanceof Request ? input : new Request(input);
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response(null, { status: 405, headers: { Allow: "GET, HEAD" } });
      }
      const found = await fileOf(new URL(request.url).pathname);
      if (!found) return new Response("Not Found", { status: 404, headers: { "Content-Type": "text/plain" } });
      const etag = `"${createHash("sha1").update(`${found.file}:${found.size}:${found.modified}`).digest("hex")}"`;
      const headers = {
        "Content-Type": TYPES[extname(found.file).toLowerCase()] ?? "application/octet-stream",
        "Cache-Control": "public, max-age=0, must-revalidate",
        ETag: etag,
      };
      const given = request.headers.get("If-None-Match");
      if (given !== null && etagListHas(given, etag.slice(1, -1))) {
        return new Response(null, { status: 304, headers });
      }
      const body = request.method === "HEAD" ? null : await readFile(found.file);
      return new Response(body, { status: 200, headers: { ...headers, "Content-Length": String(found.size) } });
    },
  };
}

// ---- the rate limiter -----------------------------------------------------------------------------

/** The rate limiter's binding, allowing everything. */
export const allowAll = { async limit() { return { success: true }; } };

// ---- the platform ---------------------------------------------------------------------------------

/** A Request as the Worker gets it on Cloudflare: asset-first unless `run_worker_first` names the
 * path, the client's address in CF-Connecting-IP. Returns the platform's `fetch(request, address)`. */
export function platform({ env, config, module = worker }) {
  const assets = config.assets ?? {};
  const ctx = { waitUntil() {}, passThroughOnException() {} };
  return async (request, address) => {
    const headers = new Headers(request.headers);
    headers.set("CF-Connecting-IP", address);
    const seen = new Request(request, { headers });
    const { pathname } = new URL(seen.url);
    if (!runsWorkerFirst(assets.run_worker_first, pathname) && await env.ASSETS.has(pathname)) {
      return env.ASSETS.fetch(seen);
    }
    return module.fetch(seen, env, ctx);
  };
}

const HOP_BY_HOP = new Set(["connection", "keep-alive", "transfer-encoding", "upgrade", "expect", "te", "trailer",
                            "proxy-connection", "proxy-authorization", "proxy-authenticate", "http2-settings"]);

/** Serve the Worker on `host:port` (0: any free port). Resolves to `{ origin, close }`. */
export async function serve({ port = 0, host = "127.0.0.1", assets, store = null, config = null, bucket = null,
                              limiter = allowAll } = {}) {
  if (!assets) throw new Error("serve: the assets folder is required");
  config ??= await readConfig();
  const env = {
    ...(config.vars ?? {}),
    SHARES: bucket ?? new LocalBucket(store),
    ASSETS: localAssets(assets),
    LIMITER: limiter,
  };
  const answer = platform({ env, config });
  const server = createServer(async (incoming, outgoing) => {
    try {
      const headers = new Headers();
      for (const [name, value] of Object.entries(incoming.headers)) {
        if (HOP_BY_HOP.has(name) || value === undefined) continue;
        for (const each of Array.isArray(value) ? value : [value]) headers.append(name, each);
      }
      const hasBody = incoming.method !== "GET" && incoming.method !== "HEAD";
      const request = new Request(new URL(incoming.url, `http://${incoming.headers.host ?? `${host}:${port}`}`), {
        method: incoming.method,
        headers,
        body: hasBody ? Readable.toWeb(incoming) : undefined,
        duplex: "half",
      });
      const response = await answer(request, incoming.socket.remoteAddress ?? "");
      outgoing.writeHead(response.status, Object.fromEntries(response.headers));
      if (response.body && incoming.method !== "HEAD") {
        for await (const chunk of response.body) outgoing.write(chunk);
      }
      outgoing.end();
    } catch (error) {
      // Its kind alone: an error's message may quote what the request carried.
      console.error(`share: ${error?.name ?? "Error"} answering a request`);
      if (!outgoing.headersSent) outgoing.writeHead(500, { "Content-Type": "application/json" });
      outgoing.end(outgoing.headersSent ? undefined : JSON.stringify({ error: "internal", hint: "See the server's log." }));
    }
  });
  await new Promise((done, failed) => {
    server.once("error", failed);
    server.listen(port, host, done);
  });
  const bound = server.address();
  const origin = `http://${bound.family === "IPv6" ? `[${bound.address}]` : bound.address}:${bound.port}`;
  return {
    origin,
    env,
    close: () => new Promise((done) => { server.close(() => done()); server.closeAllConnections(); }),
  };
}
