import { defineConfig } from 'vite';

// The shell a host keeps as the CAD app's resource (src/shell.ts, src/host/shell.ts): one small page,
// its one script inline, built beside the app (vite.config.mjs) into dist/shell.html. It loads the app
// the engine serves (app.js), so a page a host cached runs the engine's release.
function inlineShell() {
  return {
    name: 'cad-shell-inline', enforce: 'post',
    generateBundle: { order: 'post', handler(_, bundle) {
      const html = bundle['shell.html'];
      const chunks = Object.values(bundle).filter(item => item.type === 'chunk');
      if (!html || html.type !== 'asset') throw new Error('The CAD app shell build needs shell.html.');
      if (chunks.length !== 1) throw new Error(`The CAD app shell is one script: ${chunks.map(chunk => chunk.fileName)}`);
      const [script] = chunks;
      html.source = String(html.source).replace(/<script\b[^>]*\bsrc="[^"]+"[^>]*><\/script>/,
        () => `<script type="module">${script.code.replace(/<\/script/gi, '<\\/script')}</script>`);
      delete bundle[script.fileName];
      const external = Object.keys(bundle).filter(name => name !== 'shell.html');
      if (external.length) throw new Error(`Everything the CAD app shell loads must be inside shell.html: ${external.join(', ')}`);
    } },
  };
}

export default defineConfig({
  plugins: [inlineShell()],
  build: {
    emptyOutDir: false, modulePreload: false, assetsInlineLimit: Infinity, sourcemap: false,
    rolldownOptions: { input: 'shell.html' },
  },
});
