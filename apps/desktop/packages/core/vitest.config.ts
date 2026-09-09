import { resolve } from 'node:path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  resolve: {
    alias: {
      'better-sqlite3': resolve(
        __dirname,
        '../../apps/emdash-desktop/tooling/node-deps/node_modules/better-sqlite3'
      ),
    },
  },
  test: {
    environment: 'node',
    include: ['**/*.test.ts', '**/*.test.tsx'],
  },
});
