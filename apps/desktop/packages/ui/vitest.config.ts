import { resolve } from 'node:path';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';
// vite's defineConfig (not vitest/config's) so the vanilla-extract plugin
// types resolve against the same vite version; no `test` options are needed.
import { defineConfig } from 'vite';

const root = resolve(__dirname, 'src');

// Mirrors the resolve setup of vite.lib.config.ts so tests can import
// components (and their .css.ts styles), without pulling in the lib build
// or dts emission.
export default defineConfig({
  resolve: {
    alias: {
      '@': root,
      '@react': resolve(root, 'react'),
      '@styles': resolve(root, 'styles'),
      '@theme': resolve(root, 'theme'),
    },
  },
  plugins: [vanillaExtractPlugin()],
});
