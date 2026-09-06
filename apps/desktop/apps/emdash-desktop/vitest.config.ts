import { resolve } from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import { playwright } from '@vitest/browser-playwright';
import { defineConfig } from 'vitest/config';

const alias = {
  '@': resolve(__dirname, 'src'),
  '@core': resolve(__dirname, 'src/core'),
  '@root': resolve(__dirname, '.'),
  '@renderer': resolve(__dirname, 'src/renderer'),
  '@main': resolve(__dirname, 'src/main'),
  '@tooling': resolve(__dirname, 'tooling'),
};

const skipBrowserProjects = Boolean(process.env.CI || process.env.EMDASH_TEST_SKIP_BROWSER);

// Node-environment Vitest projects run without Electron. Redirect better-sqlite3 to
// the isolated system-Node build and make Electron unavailable unless a test injects it.
// The root native dependencies stay Electron-compiled for app development.
const systemNodeAlias = {
  ...alias,
  'better-sqlite3': resolve(__dirname, 'tooling/node-deps/node_modules/better-sqlite3'),
  electron: resolve(__dirname, 'tooling/vitest/electron-system-node.ts'),
};

export default defineConfig({
  // Renderer browser tests must exercise the same generated utility sheet as
  // the packaged Electron renderer. Without the Tailwind transform, classes
  // such as rounded-md exist in JSX but compute to the browser's square
  // default, so interaction-state regressions are invisible to the suite.
  plugins: [tailwindcss()],
  resolve: { alias },
  test: {
    projects: [
      {
        // All existing tests that run in a Node.js environment.
        // Migration tests are excluded — run them via `pnpm run test:migrations`.
        // DB integration tests (*.db.test.ts) are excluded — run under the main-db project.
        // Uses systemNodeAlias so native dependencies resolve to their system-Node
        // test implementations without requiring an installed Electron runtime.
        extends: true,
        resolve: { alias: systemNodeAlias },
        test: {
          name: 'node',
          environment: 'node',
          setupFiles: [resolve(__dirname, 'tooling/vitest/setup-app-config.ts')],
          include: ['src/**/*.test.ts'],
          exclude: [
            '**/_*/**',
            '**/*.db.test.ts',
            '**/*.browser.test.ts',
            'src/renderer/tests/browser/**',
            'src/main/db/tests/migrations/**',
            'src/main/core/**/*.db.test.ts',
          ],
        },
      },
      {
        // Main-process integration tests that need a real SQLite connection.
        // Uses systemNodeAlias so native dependencies resolve to their system-Node
        // test implementations without requiring an installed Electron runtime.
        extends: true,
        resolve: { alias: systemNodeAlias },
        test: {
          name: 'main-db',
          environment: 'node',
          setupFiles: [resolve(__dirname, 'tooling/vitest/setup-app-config.ts')],
          include: [
            'src/core/features/**/*.db.test.ts',
            'src/core/services/**/*.db.test.ts',
            'src/main/core/**/*.db.test.ts',
            'src/main/host/**/*.db.test.ts',
            'src/services/**/*.db.test.ts',
          ],
        },
      },
      {
        // Fixture generator — run explicitly via `pnpm run db:fixtures`.
        extends: true,
        resolve: { alias: systemNodeAlias },
        test: {
          name: 'fixtures',
          environment: 'node',
          setupFiles: [resolve(__dirname, 'tooling/vitest/setup-app-config.ts')],
          include: ['tooling/generate-fixtures.ts'],
        },
      },
      {
        // Migration tests — run explicitly via `pnpm run test:migrations`.
        extends: true,
        resolve: { alias: systemNodeAlias },
        test: {
          name: 'migrations',
          environment: 'node',
          setupFiles: [resolve(__dirname, 'tooling/vitest/setup-app-config.ts')],
          include: ['src/main/db/tests/migrations/**/*.test.ts'],
        },
      },
      {
        // Release script unit tests (artifacts, version helpers).
        extends: true,
        resolve: { alias: systemNodeAlias },
        test: {
          name: 'scripts',
          environment: 'node',
          include: ['scripts/**/*.test.ts'],
        },
      },
      // CI omits the browser project until Playwright provisioning is proven
      // stable there. EMDASH_TEST_SKIP_BROWSER provides the same escape hatch
      // for local runs.
      ...(skipBrowserProjects
        ? []
        : [
            {
              // Renderer tests that need a real browser environment (real CSS
              // layout, ResizeObserver, requestAnimationFrame, WebGL), plus
              // slice-isolation tests colocated with core slices as
              // *.browser.test.{ts,tsx}.
              extends: true as const,
              test: {
                name: 'browser',
                browser: {
                  enabled: true,
                  provider: playwright(),
                  headless: true,
                  instances: [{ browser: 'chromium' }],
                },
                include: [
                  'src/renderer/tests/browser/**/*.test.{ts,tsx}',
                  'src/core/**/*.browser.test.{ts,tsx}',
                ],
              },
            },
          ]),
    ],
  },
});
