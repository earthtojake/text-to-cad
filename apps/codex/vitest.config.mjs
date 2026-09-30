import { defineConfig } from 'vitest/config';

// The page's own units in jsdom; the build's inlining plugins are for `vite build` alone.
export default defineConfig({
  test: { include: ['src/**/*.test.ts', 'src/**/*.test.tsx'], environment: 'jsdom' },
});
