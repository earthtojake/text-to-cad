import { defineConfig } from 'vite';
import { shellWords } from './scripts/shell-words.mjs';
import { inlineShell } from './vite.shell.config.mjs';

// The CAD app as a Claude artifact (src/artifact.ts, src/host/artifact.ts): the shell (vite.shell.config.mjs)
// with the artifact's bridge, one page with its one script inline, built beside the app into dist/artifact.html.
// It loads the app the engine serves (app.js), as the shell does.
export default defineConfig({
  plugins: [shellWords(), inlineShell('artifact.html')],
  build: {
    emptyOutDir: false, modulePreload: false, assetsInlineLimit: Infinity, sourcemap: false,
    rolldownOptions: { input: 'artifact.html' },
  },
});
