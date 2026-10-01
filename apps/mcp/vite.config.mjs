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

// Fold the build into index.html. The scripts are split where the app imports lazily (each
// renderer, the drawing editor, its diagram and maths libraries), and each chunk is a gzip'd
// string the page inflates into a blob module only when something imports it: a view parses
// what it shows, not the thirteen megabytes it might. A blob URL has no directory to resolve
// "./chunk.js" against, so the build rewrites each chunk's static imports to a placeholder the
// loader swaps for its dependency's blob URL, and each dynamic import to the loader itself;
// the rewrites must account for exactly the imports rolldown recorded, or the build fails.
// Styles go inline, and workers another worker starts as blob URLs of their own. The base64
// is decoded natively where the browser can (`Uint8Array.fromBase64`), else by a plain loop.
const CHUNK = 'cad-chunk:';
const DYNAMIC_IMPORT = /\bimport\(\s*([`"'])\.\/([^`"'\s]+\.js)\1\s*\)/g;
const STATIC_IMPORT = /\b(from|import)\s*(["'])\.\/([^"'\s]+\.js)\2/g;
const LOADER = `const decode=t=>{if(Uint8Array.fromBase64)return Uint8Array.fromBase64(t);const s=atob(t),o=new Uint8Array(s.length);for(let i=0;i<s.length;i++)o[i]=s.charCodeAt(i);return o};
const loaded=new Map();
const load=f=>{let p=loaded.get(f);if(!p){p=Promise.all([new Response(new Blob([decode(SOURCES[f])]).stream().pipeThrough(new DecompressionStream('gzip'))).text(),Promise.all(IMPORTS[f].map(load))]).then(([s,urls])=>{IMPORTS[f].forEach((d,i)=>{s=s.replaceAll(JSON.stringify(${JSON.stringify(CHUNK)}+d),JSON.stringify(urls[i]))});return URL.createObjectURL(new Blob([s],{type:'text/javascript'}))});loaded.set(f,p)}return p};
globalThis.__cadImport=f=>load(f).then(u=>import(u));
await import(await load(ENTRY));`;

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
      const chunks = Object.values(bundle).filter(item => item.type === 'chunk');
      const base = fileName => fileName.split('/').pop();
      const known = new Set(chunks.map(chunk => base(chunk.fileName)));
      const sources = {}, imports = {};
      let entry = null;
      for (const chunk of chunks) {
        const name = base(chunk.fileName);
        if (/__VITE_[A-Z_]+__/.test(chunk.code)) throw new Error(`The CAD app chunk ${name} is unfinished.`);
        const statics = new Set(), dynamics = new Set();
        const code = chunk.code
          .replace(DYNAMIC_IMPORT, (_, _quote, file) => { dynamics.add(file); return `__cadImport(${JSON.stringify(file)})`; })
          .replace(STATIC_IMPORT, (_, keyword, _quote, file) => { statics.add(file); return `${keyword}${JSON.stringify(CHUNK + file)}`; });
        const same = (found, recorded) => found.size === recorded.length && recorded.every(file => found.has(base(file)));
        if (!same(statics, chunk.imports) || !same(dynamics, chunk.dynamicImports) || [...statics, ...dynamics].some(file => !known.has(file))) {
          throw new Error(`The CAD app could not account for the imports of ${name}: found ${[...statics]} / ${[...dynamics]}, recorded ${chunk.imports} / ${chunk.dynamicImports}`);
        }
        sources[name] = gzipSync(code, { level: 9 }).toString('base64');
        imports[name] = [...statics];
        if (chunk.isEntry) entry = name;
        delete bundle[chunk.fileName];
      }
      if (!entry) throw new Error('The CAD app build has no entry chunk.');
      const bootstrap = `const SOURCES=${JSON.stringify(sources)},IMPORTS=${JSON.stringify(imports)},ENTRY=${JSON.stringify(entry)};\n${LOADER}`;
      document = document.replace(/<script\b[^>]*\bsrc="[^"]+"[^>]*><\/script>/, () => `<script type="module">${bootstrap}</script>`);
      for (const [name, item] of Object.entries(bundle)) {
        if (item.type === 'asset' && name.endsWith('.css')) {
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
  build: { assetsInlineLimit: Infinity, cssCodeSplit: false, modulePreload: false },
  worker: { format: 'es', rolldownOptions: { output: { codeSplitting: false } } },
});
