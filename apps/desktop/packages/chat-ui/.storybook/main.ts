import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { StorybookConfig } from 'storybook-solidjs-vite';
import { mergeConfig } from 'vite';

const dir = dirname(fileURLToPath(import.meta.url));

const config: StorybookConfig = {
  stories: ['../src/**/*.mdx', '../src/**/*.stories.@(ts|tsx)'],
  addons: ['@storybook/addon-docs'],
  framework: 'storybook-solidjs-vite',
  // NOTE: do not register vanillaExtractPlugin() here. Storybook's vite builder
  // auto-loads the package vite.config.ts, which already provides it; adding it
  // again spawns a second VE compiler and triggers intermittent "No CSS for
  // file" resolveId races on startup.
  viteFinal: (config) =>
    mergeConfig(config, {
      // Warm up the global stylesheet chain at server start. The VE plugin's
      // resolveId for a virtual `*.vanilla.css` throws ("No CSS for file") when
      // the parent .css.ts has not been transformed yet, which the preview's
      // bootstrap imports hit on a cold start. Pre-transforming them populates
      // the VE CSS map before the browser requests the virtual CSS. (Safe only
      // because optimizeDeps now pre-bundles the VE runtimes, so warmup no
      // longer triggers a dep re-optimization that would reset the compiler.)
      // Listed explicitly rather than globbed so warmup never pre-transforms
      // variable-theme-contract.css.ts, whose function export trips Vite's SSR
      // "Invalid exports" check.
      server: {
        warmup: {
          clientFiles: [
            './src/styles/reset.css.ts',
            './src/styles/theme.css.ts',
            './src/styles/effects.css.ts',
            './src/styles/global.css.ts',
            './src/styles/storybook.css.ts',
          ],
        },
      },
      resolve: {
        alias: {
          '@components': resolve(dir, '../src/components'),
          '@core': resolve(dir, '../src/core'),
          '@lib': resolve(dir, '../src/lib'),
          '@state': resolve(dir, '../src/state'),
          '@styles': resolve(dir, '../src/styles'),
          '@': resolve(dir, '../src'),
        },
      },
    }),
};

export default config;
