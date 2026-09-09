import fs from 'node:fs/promises';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { build } from 'esbuild';

export async function buildLibrary(root, { css = false } = {}) {
  const src = path.join(root, 'src');
  const dist = path.join(root, 'dist');
  const entries = [];
  const assets = [];
  async function walk(dir) {
    for (const item of await fs.readdir(dir, { withFileTypes: true })) {
      const file = path.join(dir, item.name);
      if (item.isDirectory()) {
        if (!['__tests__', 'tests', 'harness'].includes(item.name)) await walk(file);
      } else if (!/\.(test|spec)\./.test(file)) {
        if (/\.[jt]sx?$/.test(file) && !file.endsWith('.d.ts')) entries.push(file);
        else assets.push(file);
      }
    }
  }
  await walk(src);
  await fs.rm(dist, { recursive: true, force: true });
  await build({entryPoints: entries, outbase: src, outdir: dist, bundle: false,
    format: 'esm', platform: 'neutral', target: 'es2022', jsx: 'automatic',
    loader: { '.js': 'jsx' }, sourcemap: true, logLevel: 'warning'});
  const require = createRequire(import.meta.url);
  const result = spawnSync(process.execPath, [require.resolve('typescript/bin/tsc'), '-p', path.join(root, 'tsconfig.json'), '--emitDeclarationOnly'], { stdio: 'inherit' });
  if (result.status !== 0) throw new Error(`Declaration build failed for ${root}`);
  // Hand-authored declarations and module-relative assets are package outputs too.
  for (const file of assets) {
    const target = path.join(dist, path.relative(src, file));
    await fs.mkdir(path.dirname(target), { recursive: true });
    await fs.copyFile(file, target);
  }
  // Emitted modules are ordinary ESM, including when the original source used
  // JSX filenames or TypeScript's extensionless relative imports.
  for (const file of entries) {
    const output = path.join(dist, path.relative(src, file).replace(/\.[jt]sx?$/, '.js'));
    let code = await fs.readFile(output, 'utf8');
    const replacements = new Map();
    for (const match of code.matchAll(/(?:from\s*|import\s*\(|import\s*)["'](\.[^"']+)["']/g)) {
      const specifier = match[1];
      if (specifier.includes('?')) continue;
      let resolved = specifier.replace(/\.[jt]sx$/, '.js').replace(/\.ts$/, '.js');
      if (!path.extname(resolved)) {
        try { await fs.access(path.resolve(path.dirname(output), resolved + '.js')); resolved += '.js'; }
        catch { try { await fs.access(path.resolve(path.dirname(output), resolved, 'index.js')); resolved += '/index.js'; } catch { /* Preserve asset or virtual references. */ } }
      }
      replacements.set(specifier, resolved);
    }
    for (const [before, after] of replacements) {
      if (before !== after) code = code.replaceAll(`"${before}"`, `"${after}"`).replaceAll(`'${before}'`, `'${after}'`);
    }
    await fs.writeFile(output, code);
  }
  if (css) {
    const { default: postcss } = await import('postcss');
    const { default: tailwind } = await import('@tailwindcss/postcss');
    const from = path.join(src, 'styles', 'globals.css');
    const result = await postcss([tailwind({base: root})]).process(await fs.readFile(from, 'utf8'), {from, to: path.join(dist, 'styles.css')});
    await fs.writeFile(path.join(dist, 'styles.css'), result.css);
  }
}
