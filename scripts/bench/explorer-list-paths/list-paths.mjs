// The desktop explorer's `listPaths` (read-ahead) against the serial walk it
// replaced, on one generated tree on this disk, in one run. Manual; not a test.
//
//   node scripts/bench/explorer-list-paths/list-paths.mjs [--runs 7] [--out tmp/explorer-list-paths/report.json]
//
// Both walks are bundled from the app's TypeScript with esbuild into tmp/
// (the app's own sources, not a copy): `listPaths` from
// apps/desktop/src/main/explorer/fs.ts, the serial walk and the tree from
// apps/desktop/tests/unit/main/list-paths-reference.ts, whose unit test checks
// the two answer the same. Both are warmed, then alternated so neither is
// always the one on a cold cache; the medians and their ratio are printed.
// Measured at 0.34 on an M-series Mac (the serial walk, 1.10 against itself).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { performance } from 'node:perf_hooks';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
// The desktop app's own esbuild, the one its build pins.
const { build } = createRequire(new URL('../../../apps/desktop/package.json', import.meta.url))('esbuild');

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
const desktop = path.join(repo, 'apps', 'desktop');

const args = { runs: '7' };
for (let i = 2; i < process.argv.length; i += 2) {
  const flag = process.argv[i];
  if (!['--runs', '--out'].includes(flag) || !process.argv[i + 1]) {
    throw new Error('Usage: list-paths.mjs [--runs 7] [--out REPORT.json]');
  }
  args[flag.slice(2)] = process.argv[i + 1];
}
const runs = Number(args.runs);
if (!Number.isInteger(runs) || runs < 1) throw new Error('--runs must be a positive integer');

const scratch = path.join(repo, 'tmp', 'explorer-list-paths');
fs.mkdirSync(scratch, { recursive: true });
const bundle = path.join(scratch, 'walks.mjs');
await build({
  stdin: {
    contents: [
      `export { listPaths } from ${JSON.stringify(path.join(desktop, 'src/main/explorer/fs.ts'))};`,
      `export { serialListPaths, writeProjectTree } from ${JSON.stringify(path.join(desktop, 'tests/unit/main/list-paths-reference.ts'))};`,
    ].join('\n'),
    resolveDir: desktop,
    loader: 'ts',
  },
  bundle: true,
  platform: 'node',
  format: 'esm',
  packages: 'external',
  outfile: bundle,
  logLevel: 'warning',
});
const { listPaths, serialListPaths, writeProjectTree } = await import(pathToFileURL(bundle).href);

const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'text-to-cad-list-paths-bench-')));
try {
  await writeProjectTree(root);
  await serialListPaths(root);
  await listPaths(root);
  const serial = [];
  const ahead = [];
  for (let run = 0; run < runs; run += 1) {
    let started = performance.now();
    await serialListPaths(root);
    serial.push(performance.now() - started);
    started = performance.now();
    await listPaths(root);
    ahead.push(performance.now() - started);
  }
  const median = (values) => [...values].sort((x, y) => x - y)[Math.floor(values.length / 2)];
  const report = {
    runs,
    serialMs: median(serial),
    aheadMs: median(ahead),
    ratio: median(ahead) / median(serial),
    samples: { serial, ahead },
  };
  console.log(`listPaths: serial ${report.serialMs.toFixed(1)} ms, read-ahead ${report.aheadMs.toFixed(1)} ms, ratio ${report.ratio.toFixed(2)}`);
  if (args.out) {
    fs.mkdirSync(path.dirname(path.resolve(args.out)), { recursive: true });
    fs.writeFileSync(args.out, `${JSON.stringify(report, null, 2)}\n`);
  }
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
