import { resolve } from 'node:path';
import { vanillaExtractPlugin } from '@vanilla-extract/vite-plugin';
import { playwright } from '@vitest/browser-playwright';
import solid from 'vite-plugin-solid';
import { defineConfig } from 'vitest/config';

const skipBrowserProjects = Boolean(process.env.CI || process.env.EMDASH_TEST_SKIP_BROWSER);

export default defineConfig({
  plugins: [vanillaExtractPlugin(), solid()],
  resolve: {
    alias: {
      '@components': resolve('src/components'),
      '@core': resolve('src/core'),
      '@lib': resolve('src/lib'),
      '@state': resolve('src/state'),
      '@styles': resolve('src/styles'),
      '@': resolve('src'),
    },
  },
  optimizeDeps: {
    // Pre-bundle the vanilla-extract runtime helpers. They are injected into
    // compiled .css.ts output, so Vite's initial dep scan never sees them; left
    // out, they are discovered lazily and trigger a mid-session re-optimization
    // + reload that resets the VE compiler and causes "No CSS for file" throws.
    include: [
      '@vanilla-extract/sprinkles/createRuntimeSprinkles',
      '@vanilla-extract/recipes/createRuntimeFn',
    ],
  },
  test: {
    projects: [
      {
        // Parity / arithmetic tests — pure Node, no DOM needed.
        // Benchmarks are excluded here because measure.bench.ts imports from
        // REGISTRY which transitively uses solid-js/web (browser-only).
        extends: true,
        test: {
          name: 'node',
          environment: 'node',
          include: ['src/**/*.test.ts'],
          css: false,
        },
        benchmark: {
          include: [],
        },
      },
      // CI omits the browser project until Playwright provisioning is proven
      // stable there. EMDASH_TEST_SKIP_BROWSER provides the same escape hatch
      // for local runs.
      ...(skipBrowserProjects
        ? []
        : [
            {
              // Measurement contract tests and benchmarks — need real browser layout.
              // Benchmarks live here (not in node) because measure.bench.ts imports
              // from REGISTRY which transitively uses solid-js/web.
              extends: true as const,
              test: {
                name: 'browser',
                browser: {
                  enabled: true,
                  provider: playwright(),
                  headless: true,
                  instances: [{ browser: 'chromium' }],
                },
                include: ['src/**/*.contract.test.tsx'],
                setupFiles: ['src/tests/contract-setup.ts'],
              },
              benchmark: {
                include: ['src/**/*.bench.ts'],
                browser: {
                  enabled: true,
                  provider: playwright(),
                  headless: true,
                  instances: [{ browser: 'chromium' }],
                },
              },
            },
          ]),
      {
        // Performance + memory tests — informational only, excluded from `pnpm test`.
        // Run with `pnpm --filter @emdash/chat-ui run test:perf`.
        extends: true,
        test: {
          name: 'perf',
          browser: {
            enabled: true,
            provider: playwright(),
            headless: true,
            instances: [{ browser: 'chromium' }],
          },
          include: ['src/tests/perf/**/*.perf.test.tsx'],
          setupFiles: ['src/tests/contract-setup.ts'],
        },
      },
    ],
  },
});
