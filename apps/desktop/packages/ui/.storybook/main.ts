import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { StorybookConfig } from '@storybook/react-vite';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';
import { mergeConfig } from 'vite';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const root = resolve(__dirname, '../src');

const config: StorybookConfig = {
  stories: ['../src/react/**/*.mdx', '../src/react/**/*.stories.tsx'],
  addons: ['@storybook/addon-docs'],
  framework: {
    name: '@storybook/react-vite',
    options: {},
  },
  viteFinal: (config) =>
    mergeConfig(config, {
      plugins: [vanillaExtractPlugin()],
      resolve: {
        alias: {
          '@': root,
          '@react': resolve(root, 'react'),
          '@styles': resolve(root, 'styles'),
          '@theme': resolve(root, 'theme'),
        },
      },
      // Pre-bundle VE runtime modules so Vite doesn't re-optimize them mid-render
      // (which would duplicate React and cause a `useState` null crash in Storybook).
      optimizeDeps: {
        include: [
          '@vanilla-extract/sprinkles/createRuntimeSprinkles',
          '@vanilla-extract/recipes/createRuntimeFn',
        ],
      },
    }),
};

export default config;
