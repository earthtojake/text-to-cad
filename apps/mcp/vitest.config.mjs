import { defineConfig } from 'vitest/config';
import { shellWords } from './scripts/shell-words.mjs';

// The page's own units in jsdom; the build's inlining plugins are for `vite build` alone, and the shell's words
// (`virtual:cad-shell-words`) are read as its build reads them.
export default defineConfig({
  plugins: [shellWords()],
  test: { include: ['src/**/*.test.ts', 'src/**/*.test.tsx'], environment: 'jsdom' },
});
