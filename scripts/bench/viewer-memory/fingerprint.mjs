import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');

function fingerprint(roots, ignored = new Set()) {
  const hash = createHash('sha256');
  function visit(directory) {
    if (!fs.existsSync(directory)) return;
    for (const entry of fs.readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (ignored.has(entry.name)) continue;
      const file = path.join(directory, entry.name);
      if (entry.isDirectory()) visit(file);
      else if (entry.isFile()) hash.update(path.relative(repo, file)).update('\0').update(fs.readFileSync(file)).update('\0');
    }
  }
  roots.forEach(root => visit(path.join(repo, root)));
  return hash.digest('hex');
}

export function viewerRuntimeFingerprint() {
  return {
    source: fingerprint(['apps/viewer/src', 'packages/cadgen-js/src', 'packages/cadgen/src/cadgen'], new Set(['_runtime', '__pycache__'])),
    builtClient: fingerprint(['apps/viewer/dist']),
    installedDependencies: Object.fromEntries(['apps/viewer', 'packages/cadgen-js'].map(root => [root,
      Object.fromEntries(['three', 'three-mesh-bvh', 'react'].map(name => {
        const file = path.join(repo, root, 'node_modules', name, 'package.json');
        if (!fs.existsSync(file)) return [name, null];
        const bytes = fs.readFileSync(file);
        return [name, {
          version: JSON.parse(bytes).version,
          packageJson: fs.realpathSync(file),
          packageJsonSha256: createHash('sha256').update(bytes).digest('hex'),
        }];
      }))
    ])),
  };
}

// A disk fingerprint alone cannot prove which checkout a long-lived server
// serves. Validate its entry document and referenced assets before measuring.
export async function verifyServedViewerClient(origin, {
  dist = path.join(repo, 'apps/viewer/dist'), fetchImpl = fetch,
} = {}) {
  const localIndex = fs.readFileSync(path.join(dist, 'index.html'));
  const assets = [...localIndex.toString().matchAll(/(?:src|href)="(\/assets\/[^"?#]+)"/g)].map(match => match[1]);
  const paths = ['/', ...new Set(assets)];
  const files = [];
  for (const pathname of paths) {
    const response = await fetchImpl(new URL(pathname, origin), { signal: AbortSignal.timeout(5000), cache: 'no-store' });
    if (!response.ok) throw new Error(`Served client proof failed: ${pathname} returned ${response.status}`);
    const bytes = Buffer.from(await response.arrayBuffer());
    const local = pathname === '/' ? localIndex : fs.readFileSync(path.join(dist, pathname));
    const sha256 = createHash('sha256').update(bytes).digest('hex');
    if (!bytes.equals(local)) throw new Error(`Served client differs from ${dist}: ${pathname}`);
    files.push({ path: pathname, bytes: bytes.length, sha256 });
  }
  return { dist, matches: true, files };
}
