import { gzipSync } from 'node:zlib';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { drawingAssetFiles, localizeDrawingFontFallback } from '@text-to-cad/ui/drawing-assets';

// An MCP App is one HTML resource with no asset directory behind it: the host renders it in a
// sandboxed frame whose only other origins are data: and blob:. So everything the page needs --
// scripts, styles, workers, fonts, images -- is inside index.html, and the build fails if
// anything would be left outside it.

// The drawing editor's fonts, as data URIs (the 12 MB Xiaolai CJK family stays out: a CJK
// glyph is then a system font, never a request).
const drawingFiles = drawingAssetFiles({ exclude: [/\/fonts\/Xiaolai\//] });
function inlineDrawingFonts() {
  const fonts = new Map(drawingFiles.filter(file => /\.(woff2|ttf)$/.test(file.fileName)).map(file => [
    './' + file.fileName.replace(/^excalidraw\//, ''),
    `data:font/${file.fileName.endsWith('.ttf') ? 'ttf' : 'woff2'};base64,${file.source.toString('base64')}`,
  ]));
  return {
    name: 'cad-app-inline-drawing-fonts', enforce: 'pre',
    transform(code, id) {
      if (!id.includes('@excalidraw/excalidraw/dist/')) return;
      const localized = localizeDrawingFontFallback(code);
      if (localized === null) return;
      return { code: localized.replace(/"(\.\/fonts\/[^"]+\.(?:woff2|ttf))"/g, (_, path) => JSON.stringify(fonts.get(path) || 'data:font/woff2;base64,')), map: null };
    },
  };
}

// The shared packages start workers with `new Worker(new URL(file, import.meta.url))`. Here
// that URL would point at the sandbox, so each one becomes Vite's inline (blob) worker.
function inlineWorkers() {
  return {
    name: 'cad-app-inline-workers', enforce: 'pre',
    transform(code, id) {
      if (!/\.[cm]?jsx?$/.test(id) || !code.includes('new Worker')) return;
      const imports = [];
      const result = code.replace(/new Worker\(\s*new URL\(\s*(["'])([^"']+)\1\s*,\s*import\.meta\.url\s*\)\s*,\s*\{\s*type:\s*(["'])module\3\s*\}\s*\)/g, (_, _quote, file) => {
        const name = `__cadInlineWorker${imports.length}`;
        imports.push(`import ${name} from ${JSON.stringify(`${file}?worker&inline`)};`);
        return `new ${name}()`;
      });
      return imports.length ? { code: `${imports.join('\n')}\n${result}`, map: null } : undefined;
    },
  };
}

// Fold the build into index.html: the script as a gzip'd module the page inflates and imports
// from a blob (a third of the bytes, and no HTML parser surprises inside ten megabytes of
// script), the styles inline, and workers another worker starts as blob URLs of their own.
function inlineDocument() {
  return {
    name: 'cad-app-inline-document', enforce: 'post',
    generateBundle: { order: 'post', handler(_, bundle) {
      const html = bundle['index.html'];
      if (!html || html.type !== 'asset') throw new Error('The CAD app build needs index.html.');
      let document = String(html.source);
      for (const [workerName, worker] of Object.entries(bundle)) {
        if (!workerName.endsWith('.js') || worker.type !== 'asset') continue;
        const expression = `URL.createObjectURL(new Blob([${JSON.stringify(String(worker.source))}],{type:'text/javascript'}))`;
        for (const item of Object.values(bundle)) if (item.type === 'chunk') {
          item.code = item.code.replaceAll(JSON.stringify('/' + workerName), expression).replaceAll(JSON.stringify(workerName), expression);
        }
        delete bundle[workerName];
      }
      for (const [name, item] of Object.entries(bundle)) {
        if (item.type === 'chunk' && item.isEntry) {
          if (/__VITE_[A-Z_]+__/.test(item.code)) throw new Error('The CAD app bundle is unfinished.');
          const compressed = gzipSync(item.code, { level: 9 }).toString('base64');
          const bootstrap = `const bytes=Uint8Array.from(atob(${JSON.stringify(compressed)}),c=>c.charCodeAt(0));
const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
const url=URL.createObjectURL(await new Response(stream).blob().then(blob=>new Blob([blob],{type:'text/javascript'})));
try{await import(url)}finally{URL.revokeObjectURL(url)}`;
          document = document.replace(/<script\b[^>]*\bsrc="[^"]+"[^>]*><\/script>/, () => `<script type="module">${bootstrap}</script>`);
          delete bundle[name];
        } else if (item.type === 'asset' && name.endsWith('.css')) {
          document = document.replace(/<link\b[^>]*\bhref="[^"]+\.css"[^>]*>/, () => `<style>${String(item.source).replace(/<\/style/gi, '<\\/style')}</style>`);
          delete bundle[name];
        }
      }
      const external = Object.keys(bundle).filter(name => name !== 'index.html');
      if (external.length) throw new Error(`Everything the CAD app loads must be inside index.html: ${external.join(', ')}`);
      const notices = drawingFiles.filter(file => file.fileName.includes('/licenses/')).map(file => `${file.fileName}\n${file.source}`).join('\n\n');
      html.source = document + `\n<!-- Bundled font licenses\n${notices.replaceAll('-->', '-- >')}\n-->`;
    } },
  };
}

export default defineConfig({
  plugins: [inlineWorkers(), inlineDrawingFonts(), react(), inlineDocument()],
  resolve: { dedupe: ['react', 'react-dom', 'three', 'lucide-react'] },
  build: { assetsInlineLimit: Infinity, cssCodeSplit: false, modulePreload: false, rolldownOptions: { output: { codeSplitting: false } } },
  worker: { format: 'es', rolldownOptions: { output: { codeSplitting: false } } },
});
