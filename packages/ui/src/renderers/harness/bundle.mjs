import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

/** Where `buildHarness` writes the bundle for every browser spec of a run (`scripts/run-tests.mjs`). */
export const HARNESS_DIR = 'CAD_UI_HARNESS_DIR';

/** The renderer harness (`index.tsx`) bundled into `folder`: `harness.js`, and `harness.css` when it has styles. */
export function buildHarness(folder) {
  return build({ entryPoints: [fileURLToPath(new URL('./index.tsx', import.meta.url))], outfile: join(folder, 'harness.js'),
    bundle: true, format: 'esm', platform: 'browser', conditions: ['production'], jsx: 'automatic',
    loader: { '.webp': 'dataurl', '.avif': 'dataurl', '.woff2': 'dataurl', '.svg': 'dataurl' } });
}

let bundled;
/**
 * The renderer harness's bundle, `{ bundle, css }`: the one the test run built (`HARNESS_DIR`), or, for
 * a spec run on its own, built here once per process.
 */
export function harnessBundle() {
  bundled ??= (async () => {
    const given = process.env[HARNESS_DIR];
    const folder = given || await mkdtemp(join(tmpdir(), 'text-to-cad-harness-'));
    try {
      if (!given) await buildHarness(folder);
      return { bundle: await readFile(join(folder, 'harness.js')), css: await readFile(join(folder, 'harness.css')).catch(() => '') };
    } finally {
      if (!given) await rm(folder, { recursive: true, force: true });
    }
  })();
  return bundled;
}
