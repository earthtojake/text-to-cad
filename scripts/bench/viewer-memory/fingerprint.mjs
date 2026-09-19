import fs from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

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
    source: fingerprint(['apps/web/src', 'packages/ui/src', 'packages/core/src', 'packages/cadgen/src/cadgen'], new Set(['_runtime', '__pycache__'])),
    builtClient: fingerprint(['apps/web/dist']),
    installedDependencies: Object.fromEntries(['apps/web', 'packages/ui', 'packages/core'].map(root => {
      const require = createRequire(path.join(repo, root, 'package.json'));
      return [root, Object.fromEntries(['three', 'three-mesh-bvh', 'react'].map(name => {
        let directory;
        try { directory = path.dirname(require.resolve(name)); }
        catch (error) {
          if (error.code === 'MODULE_NOT_FOUND') return [name, null];
          throw error;
        }
        // Packages can hide package.json with an exports map. Walk from their
        // resolved entry so hoisted and package-local installations agree.
        while (directory !== path.dirname(directory)) {
          const file = path.join(directory, 'package.json');
          if (fs.existsSync(file)) {
            const bytes = fs.readFileSync(file);
            const manifest = JSON.parse(bytes);
            if (manifest.name === name) return [name, {
              version: manifest.version,
              packageJson: fs.realpathSync(file),
              packageJsonSha256: createHash('sha256').update(bytes).digest('hex'),
            }];
          }
          directory = path.dirname(directory);
        }
        throw new Error(`Cannot locate ${name} manifest for ${root}`);
      }))];
    })),
  };
}

// A disk fingerprint alone cannot prove which checkout a long-lived server
// serves. Validate its entry document and referenced assets before measuring.
export async function verifyServedViewerClient(origin, {
  dist = path.join(repo, 'apps/web/dist'), fetchImpl = fetch,
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
