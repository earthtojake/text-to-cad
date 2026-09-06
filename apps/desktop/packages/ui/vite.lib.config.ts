import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';
import { defineConfig } from 'vite';

const root = resolve(__dirname, 'src');
import dts from 'vite-plugin-dts';

const pkg = JSON.parse(readFileSync(resolve(__dirname, 'package.json'), 'utf8')) as {
  dependencies?: Record<string, string>;
  peerDependencies?: Record<string, string>;
};

// Rollup string externals match import specifiers EXACTLY, so 'foo' does not
// externalize 'foo/bar'. Source here imports many subpaths ('@base-ui/react/dialog',
// '@tiptap/pm/state', '@emdash/theme/manifest', ...), and inlining them duplicates
// modules the app also imports directly — two copies of @base-ui/react means two
// React contexts and broken dialogs. Externalize every dependency and peer
// dependency with a subpath-tolerant regex so nothing third-party or workspace
// gets bundled into dist.
const escapeRegExp = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const externalizeDep = (name: string) => new RegExp(`^${escapeRegExp(name)}(/|$)`);
const externalDeps = [
  ...Object.keys(pkg.dependencies ?? {}),
  ...Object.keys(pkg.peerDependencies ?? {}),
  // Imported directly in src but provided transitively via @tanstack/react-form.
  '@tanstack/react-store',
].map(externalizeDep);

// @vitejs/plugin-react is intentionally omitted from the lib build.
// Vite's esbuild handles React JSX natively via tsconfig "jsx": "react-jsx".
// The plugin is only needed for Storybook (HMR / React Refresh).

export default defineConfig({
  resolve: {
    alias: {
      '@': root,
      '@react': resolve(root, 'react'),
      '@styles': resolve(root, 'styles'),
      '@theme': resolve(root, 'theme'),
    },
  },
  plugins: [
    vanillaExtractPlugin(),
    dts({
      tsconfigPath: './tsconfig.json',
      // Emit per-entry declarations into dist/ (mirroring the src/ tree).
      // Exports in package.json reference dist/src/**/*.d.ts paths accordingly.
      // Do NOT use rollupTypes: true — we have multiple public entries.
      outDirs: 'dist',
      include: ['src'],
    }),
  ],
  build: {
    lib: {
      entry: {
        react: resolve(__dirname, 'src/react/index.ts'),
        'react/chat-ui': resolve(__dirname, 'src/react/chat-ui/index.ts'),
        'react/primitives': resolve(__dirname, 'src/react/primitives/index.ts'),
        'react/components': resolve(__dirname, 'src/react/components/index.ts'),
        'react/patterns': resolve(__dirname, 'src/react/patterns/index.ts'),
        'react/form': resolve(__dirname, 'src/react/patterns/form/index.ts'),
        'styles/recipes/control': resolve(__dirname, 'src/styles/recipes/control.ts'),
        'styles/recipes/input': resolve(__dirname, 'src/styles/recipes/input.ts'),
        'styles/recipes/surface': resolve(__dirname, 'src/styles/recipes/surface.css.ts'),
        'styles/recipes/card': resolve(__dirname, 'src/styles/recipes/card.css.ts'),
        'styles/recipes/box': resolve(__dirname, 'src/styles/recipes/box.ts'),
        'styles/recipes/menu-item': resolve(__dirname, 'src/styles/recipes/menu-item.css.ts'),
        // VE theme utilities — exports sx (Sprinkles) and vars (theme contract).
        // Importing this entry causes style.css to include the extracted VE atoms.
        'styles/utilities/sprinkles': resolve(__dirname, 'src/styles/utilities/sprinkles.css.ts'),
        'styles/utilities': resolve(__dirname, 'src/styles/utilities/index.ts'),
      },
      formats: ['es'],
    },
    rollupOptions: {
      external: [
        ...externalDeps,
        // Transitive scopes that may surface in output beyond declared deps.
        /^@fontsource/,
        /^@shikijs\//,
      ],
      output: {
        // Rename the bundled stylesheet so consumers import '@emdash/ui/style.css'.
        assetFileNames: (assetInfo) => {
          if (assetInfo.names?.some((n) => n.endsWith('.css'))) return 'style.css';
          return '[name][extname]';
        },
      },
    },
    // Emit a single style.css containing all VE and global styles.
    cssCodeSplit: false,
    sourcemap: true,
  },
});
