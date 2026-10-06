import { defineConfig } from 'vitest/config';

// The server's units and the viewer page's run in Node (a file that needs the DOM says so with
// `// @vitest-environment jsdom`). Two tests are end to end: the real local sandbox building a
// box (test/e2e.test.ts) and a real Chromium over a real export and the built page
// (test/viewer.browser.test.ts); each sets its own timeout. Files run one at a time: both
// end-to-end tests start kernel processes.
export default defineConfig({
  test: {
    include: ['server/**/*.test.ts', 'web/**/*.test.{ts,tsx}', 'test/**/*.test.ts'],
    environment: 'node',
    fileParallelism: false,
    testTimeout: 20_000,
    hookTimeout: 30_000,
  },
});
