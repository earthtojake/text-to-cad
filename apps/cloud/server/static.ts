// What the node entry serves besides the app: the built viewer page's assets from dist/,
// and the fs store's objects at /o/<key> (on Vercel, dist/ is static output and objects
// live in R2).
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import type { Context } from 'hono';
import { IMMUTABLE, asBody, assertKey, type ObjectStore } from './store.ts';

const ASSET_TYPES: Record<string, string> = {
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.wasm': 'application/wasm',
  '.txt': 'text/plain; charset=utf-8',
  '.map': 'application/json',
};

/** A file under `distDir` for this request path, or null (index.html is the app's, never served raw). */
export async function serveDist(c: Context, distDir: string): Promise<Response | null> {
  let pathname: string;
  try {
    pathname = decodeURIComponent(new URL(c.req.url).pathname);
  } catch {
    return null;
  }
  if (pathname === '/' || pathname.endsWith('/index.html') || pathname.includes('\0')) return null;
  const root = path.resolve(distDir);
  const file = path.resolve(root, `.${pathname}`);
  if (!file.startsWith(root + path.sep)) return null;
  try {
    const info = await stat(file);
    if (!info.isFile()) return null;
  } catch {
    return null;
  }
  const type = ASSET_TYPES[path.extname(file).toLowerCase()] ?? 'application/octet-stream';
  return new Response(await readFile(file), {
    headers: {
      'content-type': type,
      'cache-control': pathname.startsWith('/assets/') ? IMMUTABLE : 'no-cache',
      'x-content-type-options': 'nosniff',
    },
  });
}

/** GET /o/<key> for the fs store. Stored bytes are someone's upload: never render them here. */
export async function serveFsObject(c: Context, store: ObjectStore): Promise<Response> {
  let key: string;
  try {
    key = assertKey(decodeURIComponent(new URL(c.req.url).pathname.replace(/^\/o\//, '')));
  } catch {
    return c.json({ error: 'not found' }, 404);
  }
  const object = await store.get(key);
  if (!object) return c.json({ error: 'not found' }, 404);
  return new Response(c.req.method === 'HEAD' ? null : asBody(object.bytes), {
    headers: {
      'content-type': object.type,
      'content-length': String(object.bytes.byteLength),
      'cache-control': IMMUTABLE,
      'access-control-allow-origin': '*',
      'x-content-type-options': 'nosniff',
      'content-security-policy': "sandbox; default-src 'none'",
    },
  });
}
