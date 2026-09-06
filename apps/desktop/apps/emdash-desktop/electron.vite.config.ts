import { cp, rm } from 'node:fs/promises';
import { basename, extname, resolve } from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'electron-vite';
import { desktopWorkers } from './src/core/manifests/node/workers';

function desktopWorkerBuildInputs(): Record<string, string> {
  return Object.fromEntries(
    Object.values(desktopWorkers).map((worker) => [
      basename(worker.file, extname(worker.file)),
      resolve(worker.entry),
    ])
  );
}

function copyAdapterAssetsPlugin() {
  return {
    name: 'copy-plugin-adapter-assets',
    async closeBundle(): Promise<void> {
      const source = resolve('../../packages/plugins/dist/adapters');
      const target = resolve('out/main/adapters');
      try {
        await rm(target, { recursive: true, force: true });
        await cp(source, target, { recursive: true });
      } catch (error) {
        if (isNodeError(error) && error.code === 'ENOENT') return;
        throw error;
      }
    },
  };
}

function isNodeError(error: unknown): error is NodeJS.ErrnoException {
  return error instanceof Error && 'code' in error;
}

// Workspace packages must be bundled (not externalized) in main/preload builds:
// externalized modules are resolved by Node at runtime, where the `development`
// export condition is off, so dev runs would silently load stale dists.
const workspacePackages = [
  '@emdash/chat-ui',
  '@emdash/core',
  '@emdash/plugins',
  '@emdash/shared',
  '@emdash/theme',
  '@emdash/ui',
  '@emdash/wire',
];

export default defineConfig({
  main: {
    root: 'src/main',
    envDir: resolve('.'),
    plugins: [copyAdapterAssetsPlugin()],
    build: {
      emptyOutDir: true,
      externalizeDeps: {
        exclude: workspacePackages,
      },
      rollupOptions: {
        input: {
          index: resolve('src/entry/main.ts'),
          ...desktopWorkerBuildInputs(),
        },
        output: {
          entryFileNames: '[name].js',
        },
      },
    },
    resolve: {
      alias: {
        '@': resolve('src'),
        '@core': resolve('src/core'),
        '@main': resolve('src/main'),
        '@root': resolve('.'),
      },
    },
  },
  preload: {
    root: 'src/entry',
    build: {
      emptyOutDir: true,
      externalizeDeps: {
        exclude: workspacePackages,
      },
      rollupOptions: {
        input: {
          index: resolve('src/entry/preload.ts'),
        },
      },
    },
    resolve: {
      alias: {
        '@root': resolve('.'),
      },
    },
  },
  renderer: {
    root: 'src/renderer',
    plugins: [react(), tailwindcss()],
    build: {
      emptyOutDir: true,
    },
    resolve: {
      alias: {
        '@': resolve('src'),
        '@core': resolve('src/core'),
        '@renderer': resolve('src/renderer'),
        '@root': resolve('.'),
        // cli-agent-plugins metadata/icons chunks transitively reference node:buffer
        // (through hook-config helpers bundled in the same tsdown chunk), even though
        // those helpers never run in the renderer. Alias to the browser-safe polyfill.
        'node:buffer': 'buffer',
      },
    },
    server: {
      port: 3000,
    },
  },
});
