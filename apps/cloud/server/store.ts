// Object storage. Every key names immutable bytes:
//   o/<sha256>            every file (sources, outputs, export objects, images)
//   b/<build>/export.json a build's recorded viewer export
//   sketch/<sha256>.png   a sketch someone attached from the viewer
// `fs` keeps them on disk for development (served by the node entry at /o/<key>);
// `r2` keeps them in a Cloudflare R2 bucket through its S3 API.
import { mkdir, readFile, rename, stat, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { AwsClient } from 'aws4fetch';
import { randomBase62 } from './ids.ts';

export interface StoredObject {
  bytes: Uint8Array;
  type: string;
}

export interface ObjectStore {
  kind: 'fs' | 'r2';
  put(key: string, bytes: Uint8Array, type: string): Promise<void>;
  get(key: string): Promise<StoredObject | null>;
  exists(key: string): Promise<boolean>;
  /** A browser-fetchable URL for the object: relative (`/o/<key>`) for `fs`. */
  publicUrl(key: string): string;
}

export const IMMUTABLE = 'public, max-age=31536000, immutable';

/** Bytes as a fetch/Response body (TypeScript types a Uint8Array over a SharedArrayBuffer apart). */
export const asBody = (bytes: Uint8Array) => bytes as Uint8Array<ArrayBuffer>;

export function assertKey(key: string): string {
  if (
    typeof key !== 'string' || key.length === 0 || key.length > 512 || key.startsWith('/') ||
    !/^[A-Za-z0-9._/-]+$/.test(key) || key.split('/').some((part) => part === '' || part === '.' || part === '..')
  ) {
    throw new Error(`invalid object key: ${JSON.stringify(key)}`);
  }
  return key;
}

export const objectKey = (sha256: string) => `o/${sha256}`;

export interface FsStore extends ObjectStore {
  root: string;
}

export function createFsStore(root: string): FsStore {
  const dataPath = (key: string) => path.join(root, 'objects', assertKey(key));
  const typePath = (key: string) => path.join(root, 'types', assertKey(key));
  return {
    kind: 'fs',
    root,
    async put(key, bytes, type) {
      const target = dataPath(key);
      await mkdir(path.dirname(target), { recursive: true });
      await mkdir(path.dirname(typePath(key)), { recursive: true });
      await writeFile(typePath(key), type);
      const temporary = `${target}.${randomBase62(8)}.tmp`;
      await writeFile(temporary, bytes);
      await rename(temporary, target);
    },
    async get(key) {
      try {
        const [bytes, type] = await Promise.all([
          readFile(dataPath(key)),
          readFile(typePath(key), 'utf8').catch(() => 'application/octet-stream'),
        ]);
        return { bytes: new Uint8Array(bytes), type };
      } catch (error) {
        if ((error as NodeJS.ErrnoException).code === 'ENOENT') return null;
        throw error;
      }
    },
    async exists(key) {
      try {
        return (await stat(dataPath(key))).isFile();
      } catch {
        return false;
      }
    },
    publicUrl: (key) => `/o/${assertKey(key)}`,
  };
}

export interface R2Options {
  endpoint: string;
  bucket: string;
  accessKeyId: string;
  secretAccessKey: string;
  publicBaseUrl: string;
  fetch?: typeof fetch;
}

export function createR2Store(options: R2Options): ObjectStore {
  const client = new AwsClient({
    accessKeyId: options.accessKeyId,
    secretAccessKey: options.secretAccessKey,
    service: 's3',
    region: 'auto',
  });
  const send = options.fetch ?? fetch;
  const url = (key: string) =>
    `${options.endpoint}/${encodeURIComponent(options.bucket)}/${assertKey(key).split('/').map(encodeURIComponent).join('/')}`;
  async function request(key: string, init: RequestInit) {
    const signed = await client.sign(url(key), init);
    return send(signed);
  }
  return {
    kind: 'r2',
    async put(key, bytes, type) {
      const response = await request(key, {
        method: 'PUT',
        body: asBody(bytes),
        headers: { 'content-type': type, 'cache-control': IMMUTABLE },
      });
      if (!response.ok) throw new Error(`R2 PUT ${key} failed: ${response.status} ${await response.text()}`);
    },
    async get(key) {
      const response = await request(key, { method: 'GET' });
      if (response.status === 404) return null;
      if (!response.ok) throw new Error(`R2 GET ${key} failed: ${response.status}`);
      return {
        bytes: new Uint8Array(await response.arrayBuffer()),
        type: response.headers.get('content-type') ?? 'application/octet-stream',
      };
    },
    async exists(key) {
      const response = await request(key, { method: 'HEAD' });
      if (response.status === 404) return false;
      if (!response.ok) throw new Error(`R2 HEAD ${key} failed: ${response.status}`);
      return true;
    },
    publicUrl: (key) => `${options.publicBaseUrl}/${assertKey(key)}`,
  };
}

/** Store content-addressed bytes once: `o/<sha256>` is written only when absent. */
export async function putObject(store: ObjectStore, sha256: string, bytes: Uint8Array, type: string): Promise<string> {
  const key = objectKey(sha256);
  if (!(await store.exists(key))) await store.put(key, bytes, type);
  return key;
}
