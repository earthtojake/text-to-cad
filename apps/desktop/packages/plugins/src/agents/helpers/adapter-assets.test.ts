import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';
import {
  adapterAssetFileName,
  defineAdapterAsset,
  resolveAdapterAssetFromUrl,
} from './adapter-assets';

describe('adapter asset helpers', () => {
  const asset = defineAdapterAsset({
    name: 'example-acp',
    specifier: '@example/acp/dist/index.js',
    format: 'esm',
  });

  it('derives adapter file names from format', () => {
    expect(adapterAssetFileName(asset)).toBe('example-acp.mjs');
    expect(adapterAssetFileName({ ...asset, format: 'cjs' })).toBe('example-acp.cjs');
  });

  it('resolves adapters next to the consuming bundle', async () => {
    const root = await mkdtemp(join(tmpdir(), 'emdash-adapter-assets-'));
    try {
      const adapterPath = join(root, 'adapters', adapterAssetFileName(asset));
      await mkdir(join(root, 'adapters'));
      await writeFile(adapterPath, '', 'utf8');

      const resolved = resolveAdapterAssetFromUrl(
        asset,
        pathToFileURL(join(root, 'chunk.mjs')).href
      );
      expect(resolved).toBe(adapterPath);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it('resolves adapters one directory above split chunks', async () => {
    const root = await mkdtemp(join(tmpdir(), 'emdash-adapter-assets-'));
    try {
      const adapterPath = join(root, 'adapters', adapterAssetFileName(asset));
      await mkdir(join(root, 'adapters'), { recursive: true });
      await writeFile(adapterPath, '', 'utf8');

      const resolved = resolveAdapterAssetFromUrl(
        asset,
        pathToFileURL(join(root, 'chunks/chunk.mjs')).href
      );
      expect(resolved).toBe(adapterPath);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
