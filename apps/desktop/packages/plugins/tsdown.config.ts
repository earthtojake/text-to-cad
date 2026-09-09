import { createRequire } from 'node:module';
import { defineConfig } from 'tsdown';
import type { UserConfig } from 'tsdown';
import { adapterAssets } from './src/agents/adapter-manifest.ts';

const require = createRequire(import.meta.url);

const mainConfig = {
  entry: {
    agents: 'src/agents/registry.ts',
    'agents/adapter-manifest': 'src/agents/adapter-manifest.ts',
    'agents/helpers/adapter-assets': 'src/agents/helpers/adapter-assets.ts',
    'agents/helpers/adapter-validation': 'src/agents/helpers/adapter-validation.ts',
    'agents/types': 'src/agents/types.ts',
  },
  format: ['esm'],
  dts: true,
  deps: {
    neverBundle: ['zod', 'smol-toml', '@emdash/core', '@emdash/shared'],
  },
  sourcemap: true,
  clean: true,
} satisfies UserConfig;

const adapterConfigs: UserConfig[] = adapterAssets.map((asset) => ({
  entry: {
    [`adapters/${asset.name}`]: require.resolve(asset.specifier),
  },
  format: [asset.format],
  dts: false,
  sourcemap: true,
  clean: false,
  deps: {
    alwaysBundle: [/.*/],
    neverBundle: [...(asset.external ?? [])],
    onlyBundle: false,
  },
}));

export default defineConfig([mainConfig, ...adapterConfigs]);
