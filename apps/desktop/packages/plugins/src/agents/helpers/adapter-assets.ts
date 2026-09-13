import { existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export type AdapterAsset = {
  readonly name: string;
  readonly specifier: string;
  readonly format: 'esm' | 'cjs';
  readonly external?: readonly string[];
};

export function defineAdapterAsset(asset: AdapterAsset): AdapterAsset {
  return asset;
}

export function adapterAssetFileName(asset: AdapterAsset): string {
  return `${asset.name}.${asset.format === 'esm' ? 'mjs' : 'cjs'}`;
}

export function resolveAdapterAsset(asset: AdapterAsset): string {
  return resolveAdapterAssetFromUrl(asset, import.meta.url);
}

export function resolveAdapterAssetFromUrl(asset: AdapterAsset, moduleUrl: string): string {
  const fileName = adapterAssetFileName(asset);
  const moduleDirectory = dirname(fileURLToPath(moduleUrl));
  const candidates = [
    join(moduleDirectory, 'adapters', fileName),
    join(moduleDirectory, '..', 'adapters', fileName),
  ];

  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }

  return createRequire(moduleUrl).resolve(asset.specifier);
}

export function adapterAssetFileUrl(asset: AdapterAsset, directory: string): string {
  return pathToFileURL(join(directory, adapterAssetFileName(asset))).href;
}
