// The Worker's platform, locally: stand-ins for what Cloudflare gives it (the R2 bucket, the static
// assets and their `_headers`, the two rate limiters, the client's address and the asset-first routing of
// wrangler.jsonc), and a Node http server that runs the real Worker module over them. `serve.mjs` is its
// command; the tests use it directly. Each stand-in does what the Worker asks of its original, as
// Cloudflare's documentation describes it (README.md, "Cloudflare, as relied on"), and throws on what it
// does not emulate rather than doing it some other way.
//
// Like the Worker, nothing here logs a header or a body.

import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, rename, rm, stat, writeFile } from "node:fs/promises";
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

// R2's own bounds: list() answers at most 1000 objects a call, and delete() takes at most 1000 keys.
const LIST_LIMIT = 1000;
const DELETE_LIMIT = 1000;

/** An R2 bucket in memory, or in files under `directory`: `head`, `get`, `put` (with `onlyIf`,
 * `customMetadata` and `httpMetadata`), `delete` of one key or many, and `list` by prefix, page by page
 * with a cursor. Each operation is atomic, as R2's are (they run one at a time), and strongly consistent.
 * `now` is the clock objects are uploaded by. `pageSize` is the most objects one list() answers: R2 may
 * answer fewer than its limit, and a caller must follow `truncated`, which a size below 1000 tests. */
export class LocalBucket {
  #objects = new Map();
  #queue = Promise.resolve();
  #indexed = false;
  #now;

  constructor(directory = null, { now = Date.now, pageSize = LIST_LIMIT } = {}) {
    this.directory = directory ? resolve(directory) : null;
    this.pageSize = pageSize;
    this.#now = now;
  }

  head(key) {
    return this.#serial(async () => {
      const record = await this.#record(key);
      return record ? objectOf(key, record) : null;
    });
  }

  get(key, options) {
    if (options !== undefined) throw new TypeError("get: this stand-in takes no options");
    return this.#serial(async () => {
      const record = await this.#record(key);
      return record ? bodyOf(key, record, await this.#bytes(key, record)) : null;
    });
  }

  put(key, value, options = {}) {
    const { onlyIf, customMetadata = {}, httpMetadata, ...other } = options;
    notEmulated("put", other);
    for (const [name, text] of Object.entries(customMetadata)) {
      if (typeof text !== "string") throw new TypeError(`put: customMetadata.${name} is not a string`);
    }
    return this.#serial(async () => {
      const bytes = await bytesOf(value);
      const existing = await this.#record(key);
      if (!meets(onlyIf, existing)) return null;
      const record = {
        bytes,
        size: bytes.byteLength,
        etag: createHash("md5").update(bytes).digest("hex"),
        version: randomUUID().replaceAll("-", ""),
        uploaded: new Date(this.#now()).toISOString(),
        customMetadata: { ...customMetadata },
        httpMetadata: httpMetadataOf(httpMetadata),
      };
      await this.#store(key, record);
      return objectOf(key, record);
    });
  }

  /** Deletes one key or up to 1000; a key that holds nothing is no error. */
  delete(keys) {
    const each = Array.isArray(keys) ? keys : [keys];
    if (each.length > DELETE_LIMIT) return Promise.reject(new RangeError(`delete: at most ${DELETE_LIMIT} keys a call`));
    return this.#serial(async () => {
      await this.#index();
      for (const key of each) await this.#drop(key);
    });
  }

  /** The objects whose keys start with `prefix`, in lexicographic order of their bytes, at most `limit`
   * (and `pageSize`) of them; `truncated` and a `cursor` to go on from where more follow. An object's
   * metadata is listed only where `include` names it, as R2 does. */
  list(options = {}) {
    const { prefix = "", cursor, limit = LIST_LIMIT, include = [], ...other } = options;
    notEmulated("list", other);
    if (!Number.isInteger(limit) || limit < 1 || limit > LIST_LIMIT) throw new RangeError(`list: limit is 1 to ${LIST_LIMIT}`);
    return this.#serial(async () => {
      await this.#index();
      const after = cursor === undefined ? null : Buffer.from(cursor, "base64url").toString("utf8");
      const keys = [...this.#objects.keys()]
        .filter((key) => key.startsWith(prefix) && (after === null || byBytes(key, after) > 0))
        .sort(byBytes);
      const page = keys.slice(0, Math.min(limit, this.pageSize));
      const truncated = page.length < keys.length;
      return {
        objects: page.map((key) => listedOf(key, this.#objects.get(key), include)),
        truncated,
        ...(truncated ? { cursor: Buffer.from(page.at(-1), "utf8").toString("base64url") } : {}),
        delimitedPrefixes: [],
      };
    });
  }

  /** Every key held, sorted, for tests that look at what was kept. */
  keys() {
    return this.#serial(async () => {
      await this.#index();
      return [...this.#objects.keys()].sort(byBytes);
    });
  }

  #serial(operation) {
    const result = this.#queue.then(operation);
    this.#queue = result.catch(() => {});
    return result;
  }

  /** The folder's objects, read once: their metadata now, their bytes when first asked for. */
  async #index() {
    if (this.#indexed) return;
    this.#indexed = true;
    if (!this.directory) return;
    for (const file of await readdir(this.directory).catch(() => [])) {
      if (!file.endsWith(".json")) continue;
      const key = decodeURIComponent(file.slice(0, -".json".length));
      this.#objects.set(key, { ...JSON.parse(await readFile(join(this.directory, file), "utf8")), bytes: null });
    }
  }

  async #record(key) {
    await this.#index();
    return this.#objects.get(key) ?? null;
  }

  async #bytes(key, record) {
    record.bytes ??= new Uint8Array(await readFile(this.#file(key, "bin")));
    return record.bytes;
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

function notEmulated(operation, options) {
  const names = Object.keys(options);
  if (names.length) throw new TypeError(`${operation}: this stand-in does not emulate ${names.join(", ")}`);
}

function byBytes(a, b) {
  return Buffer.compare(Buffer.from(a, "utf8"), Buffer.from(b, "utf8"));
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

/** Whether a put's `onlyIf` holds: an R2Conditional, or a Headers of conditional headers. An etag to
 * match fails where there is no object; a wildcard etag (`If-None-Match: *`) matches any object. */
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
  const { etagMatches, etagDoesNotMatch, uploadedBefore, uploadedAfter, ...other } = onlyIf;
  notEmulated("onlyIf", other);
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
  return listedOf(key, record, ["customMetadata", "httpMetadata"]);
}

/** An R2Object as list() answers it: its metadata only where `include` asks for it. */
function listedOf(key, record, include) {
  return {
    key,
    version: record.version,
    size: record.size,
    etag: record.etag,
    httpEtag: `"${record.etag}"`,
    uploaded: new Date(record.uploaded),
    ...(include.includes("customMetadata") ? { customMetadata: { ...record.customMetadata } } : {}),
    ...(include.includes("httpMetadata") ? { httpMetadata: { ...record.httpMetadata } } : {}),
  };
}

function bodyOf(key, record, bytes) {
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

// Files at the root of the assets that configure them, and are never served.
const CONFIGURATION = new Set(["/_headers", "/_redirects"]);

/** The ASSETS binding over the files under `directory`, as wrangler.jsonc configures it
 * (`html_handling: "none"`, `not_found_handling: "none"`): a path answers the file at exactly that
 * path, and anything else is a 404. Only the URL's path is read. `has` and `headersFor` are the
 * platform's, not the binding's: whether a path is a file, and what `_headers` adds to it. */
export function localAssets(directory) {
  const root = resolve(directory);
  let rules = null;
  const fileOf = async (pathname) => {
    let decoded;
    try { decoded = decodeURIComponent(pathname); } catch { return null; }
    if (decoded.includes("\0") || decoded.split("/").includes("..") || CONFIGURATION.has(decoded)) return null;
    const file = resolve(root, `.${decoded}`);
    if (file !== root && !file.startsWith(root + sep)) return null;
    const found = await stat(file).catch(() => null);
    return found?.isFile() ? { file, size: found.size, modified: found.mtimeMs } : null;
  };
  return {
    async has(pathname) {
      return (await fileOf(pathname)) !== null;
    },
    async headersFor(pathname) {
      rules ??= headerRules(await readFile(join(root, "_headers"), "utf8").catch(() => ""));
      return headersOf(rules, pathname);
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

/** A `_headers` file's rules: a path pattern on a line of its own (`*` a splat), then its headers, one
 * `Name: value` a line, indented. Placeholders, absolute URLs and `! Name` lines are not emulated. */
function headerRules(text) {
  const rules = [];
  for (const [index, line] of text.split(/\r?\n/).entries()) {
    if (!line.trim() || line.trimStart().startsWith("#")) continue;
    const pattern = /^\/\S*$/.exec(line);
    const header = /^\s+([A-Za-z0-9-]+):\s*(.*?)\s*$/.exec(line);
    if (pattern && !line.includes(":")) {
      rules.push({ matches: new RegExp(`^${line.split("*").map(escapeRegExp).join(".*")}$`), headers: [] });
    } else if (header && rules.length) {
      rules.at(-1).headers.push([header[1], header[2]]);
    } else {
      throw new Error(`_headers, line ${index + 1}: this stand-in reads a path pattern, then indented "Name: value" lines`);
    }
  }
  return rules;
}

/** The headers the rules give a path, in the file's order, a name given twice joined with a comma. */
function headersOf(rules, pathname) {
  const headers = new Map();
  for (const rule of rules) {
    if (!rule.matches.test(pathname)) continue;
    for (const [name, value] of rule.headers) {
      const known = headers.get(name.toLowerCase());
      headers.set(name.toLowerCase(), known === undefined ? value : `${known}, ${value}`);
    }
  }
  return [...headers];
}

// ---- the rate limiters ----------------------------------------------------------------------------

/** A rate limiter's binding, allowing everything. */
export const allowAll = { async limit() { return { success: true }; } };

// ---- the platform ---------------------------------------------------------------------------------

/** A Request as the Worker gets it on Cloudflare: asset-first unless `run_worker_first` names the
 * path, a static answer with what `_headers` adds, the client's address in CF-Connecting-IP. Returns
 * the platform's `fetch(request, address)`. */
export function platform({ env, config, module = worker }) {
  const assets = config.assets ?? {};
  const ctx = { waitUntil() {}, passThroughOnException() {} };
  return async (request, address) => {
    const headers = new Headers(request.headers);
    headers.set("CF-Connecting-IP", address);
    const seen = new Request(request, { headers });
    const { pathname } = new URL(seen.url);
    if (!runsWorkerFirst(assets.run_worker_first, pathname) && await env.ASSETS.has(pathname)) {
      const answer = await env.ASSETS.fetch(seen);
      const added = await env.ASSETS.headersFor(pathname);
      if (!added.length) return answer;
      const given = new Response(answer.body, answer);
      for (const [name, value] of added) given.headers.set(name, value);
      return given;
    }
    return module.fetch(seen, env, ctx);
  };
}

const HOP_BY_HOP = new Set(["connection", "keep-alive", "transfer-encoding", "upgrade", "expect", "te", "trailer",
                            "proxy-connection", "proxy-authorization", "proxy-authenticate", "http2-settings"]);

/** Serve the Worker on `host:port` (0: any free port), with the bindings wrangler.jsonc names: its bucket
 * (in memory, or in files under `store`), the assets folder given, and each rate limiter, which allows
 * everything. Resolves to `{ origin, env, close }`. */
export async function serve({ port = 0, host = "127.0.0.1", assets, store = null, config = null } = {}) {
  if (!assets) throw new Error("serve: the assets folder is required");
  config ??= await readConfig();
  const env = { ...(config.vars ?? {}), ASSETS: localAssets(assets) };
  for (const { binding } of config.r2_buckets ?? []) env[binding] = new LocalBucket(store);
  for (const { name } of config.ratelimits ?? []) env[name] = allowAll;
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
