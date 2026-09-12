import { defineConfig } from 'vitest/config';
export default defineConfig({
  esbuild: { jsx: 'automatic' },
  test: { include: ['src/**/*.test.ts', 'src/**/*.test.tsx'], environment: 'jsdom', globals: true },
});
