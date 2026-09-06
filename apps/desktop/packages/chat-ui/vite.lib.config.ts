import { resolve } from 'node:path';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';
import { defineConfig } from 'vite';
import dts from 'vite-plugin-dts';
import solid from 'vite-plugin-solid';

export default defineConfig({
  plugins: [
    vanillaExtractPlugin(),
    solid(),
    dts({
      rollupTypes: true,
      tsconfigPath: './tsconfig.json',
    }),
  ],
  resolve: {
    alias: {
      '@components': resolve(__dirname, 'src/components'),
      '@core': resolve(__dirname, 'src/core'),
      '@lib': resolve(__dirname, 'src/lib'),
      '@state': resolve(__dirname, 'src/state'),
      '@styles': resolve(__dirname, 'src/styles'),
      '@': resolve(__dirname, 'src'),
    },
  },
  build: {
    lib: {
      entry: {
        index: resolve(__dirname, 'src/index.tsx'),
      },
      formats: ['es'],
    },
    rollupOptions: {
      external: ['solid-js', 'solid-js/web', 'solid-js/store', /^@fontsource/],
      output: {
        // Rename the bundled stylesheet to style.css so consumers can import
        // '@emdash/chat-ui/style.css' without knowing the internal lib name.
        assetFileNames: (assetInfo) => {
          if (assetInfo.names?.some((n) => n.endsWith('.css'))) return 'style.css';
          return '[name][extname]';
        },
      },
    },
    // Emit a single style.css containing all CSS modules and global styles.
    cssCodeSplit: false,
  },
});
