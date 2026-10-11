import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';
import remapping from '@jridgewell/remapping';
import MagicString from 'magic-string';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { buildId } from '@text-to-cad/ui/build-id';
import { stampDebugId } from '@text-to-cad/core/chunk-ids';
import { packageSourceMaps } from '@text-to-cad/core/source-maps';
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
// that URL would point at the sandbox, so each one becomes Vite's inline (blob) worker. The
// edit comes with its map (its imports push the module's code down a line), so that code keeps
// its place in the page's map.
const WORKER = /new Worker\(\s*new URL\(\s*(["'])([^"']+)\1\s*,\s*import\.meta\.url\s*\)\s*,\s*\{\s*type:\s*(["'])module\3\s*\}\s*\)/g;
function inlineWorkers() {
  return {
    name: 'cad-app-inline-workers', enforce: 'pre',
    transform(code, id) {
      if (!/\.[cm]?jsx?$/.test(id) || !code.includes('new Worker')) return;
      const edited = new MagicString(code);
      const imports = [];
      for (const match of code.matchAll(WORKER)) {
        const name = `__cadInlineWorker${imports.length}`;
        imports.push(`import ${name} from ${JSON.stringify(`${match[2]}?worker&inline`)};`);
        edited.overwrite(match.index, match.index + match[0].length, `new ${name}()`);
      }
      if (!imports.length) return;
      edited.prepend(`${imports.join('\n')}\n`);
      return { code: edited.toString(), map: edited.generateMap({ hires: true }) };
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
//
// A crash on the page names the chunk it ran in by its debug id (`IDS`, as `__cadChunkIds`; the
// crash reporter in @text-to-cad/core reads it), and the release uploads each chunk with its source
// map (`dist/sourcemaps`, scripts/release/sourcemaps.py), so PostHog can show the source -- the
// shared packages' own, since their modules load with their maps (@text-to-cad/core/source-maps)
// and rolldown chains them. The map must fit the text the page runs: every edit here is made with
// its positions kept (magic-string) and folded into rolldown's map, and a placeholder is as wide as
// the blob URL that replaces it (`WIDTH`, padded with spaces a URL's parser drops), so swapping it
// moves no code. The id is the one that text and its map decide (@text-to-cad/core/chunk-ids), never
// rolldown's: rolldown names the code before these edits, which the CAD Viewer may ship unedited
// under the same id.
const CHUNK = 'cad-chunk:';
const WIDTH = 192;
const DYNAMIC_IMPORT = /\bimport\(\s*([`"'])\.\/([^`"'\s]+\.js)\1\s*\)/g;
const STATIC_IMPORT = /\b(from|import)\s*(["'])\.\/([^"'\s]+\.js)\2/g;
const LOADER = `const decode=t=>{if(Uint8Array.fromBase64)return Uint8Array.fromBase64(t);const s=atob(t),o=new Uint8Array(s.length);for(let i=0;i<s.length;i++)o[i]=s.charCodeAt(i);return o};
const wide=t=>JSON.stringify(t.length<${WIDTH}?t.padEnd(${WIDTH}):t);
const loaded=new Map();
globalThis.__cadChunkIds=IDS;
const load=f=>{let p=loaded.get(f);if(!p){p=Promise.all([new Response(new Blob([decode(SOURCES[f])]).stream().pipeThrough(new DecompressionStream('gzip'))).text(),Promise.all(IMPORTS[f].map(load))]).then(([s,urls])=>{IMPORTS[f].forEach((d,i)=>{s=s.replaceAll(wide(${JSON.stringify(CHUNK)}+d),wide(urls[i]))});const u=URL.createObjectURL(new Blob([s],{type:'text/javascript'}));(globalThis.__cadChunks??={})[u]=f;return u});loaded.set(f,p)}return p};
globalThis.__cadImport=f=>load(f).then(u=>import(u));
await import(await load(ENTRY));`;
const wide = text => JSON.stringify(text.length < WIDTH ? text.padEnd(WIDTH) : text);

// Every occurrence of `text` in `code`, as [start, end].
function occurrences(code, text) {
  const found = [];
  for (let at = code.indexOf(text); at !== -1; at = code.indexOf(text, at + text.length)) found.push([at, at + text.length]);
  return found;
}

function inlineDocument() {
  const pairs = [];
  return {
    name: 'cad-app-inline-document', enforce: 'post',
    generateBundle: { order: 'post', handler(_, bundle) {
      const html = bundle['index.html'];
      if (!html || html.type !== 'asset') throw new Error('The CAD app build needs index.html.');
      let document = String(html.source);
      const workers = [];
      for (const [workerName, worker] of Object.entries(bundle)) {
        if (!workerName.endsWith('.js') || worker.type !== 'asset') continue;
        workers.push([workerName, `URL.createObjectURL(new Blob([${JSON.stringify(String(worker.source))}],{type:'text/javascript'}))`]);
        delete bundle[workerName];
      }
      const chunks = Object.values(bundle).filter(item => item.type === 'chunk');
      const base = fileName => fileName.split('/').pop();
      const known = new Set(chunks.map(chunk => base(chunk.fileName)));
      const sources = {}, imports = {}, ids = {};
      let entry = null;
      pairs.length = 0;
      for (const chunk of chunks) {
        const name = base(chunk.fileName);
        if (/__VITE_[A-Z_]+__/.test(chunk.code)) throw new Error(`The CAD app chunk ${name} is unfinished.`);
        const mapName = chunk.sourcemapFileName ?? `${chunk.fileName}.map`;
        // A chunk with code of its own has a map and a debug id; one that only re-exports others has
        // neither, and nothing of its own to run, so no frame of a crash is ever in it.
        const original = bundle[mapName]?.type === 'asset' ? JSON.parse(String(bundle[mapName].source)) : null;
        const statics = new Set(), dynamics = new Set();
        const edited = new MagicString(chunk.code);
        for (const [workerName, expression] of workers) {
          for (const quoted of [JSON.stringify('/' + workerName), JSON.stringify(workerName)]) {
            for (const [start, end] of occurrences(chunk.code, quoted)) edited.overwrite(start, end, expression);
          }
        }
        for (const match of chunk.code.matchAll(DYNAMIC_IMPORT)) {
          dynamics.add(match[2]);
          edited.overwrite(match.index, match.index + match[0].length, `__cadImport(${JSON.stringify(match[2])})`);
        }
        for (const match of chunk.code.matchAll(STATIC_IMPORT)) {
          statics.add(match[3]);
          edited.overwrite(match.index, match.index + match[0].length, `${match[1]}${wide(CHUNK + match[3])}`);
        }
        const same = (found, recorded) => found.size === recorded.length && recorded.every(file => found.has(base(file)));
        if (!same(statics, chunk.imports) || !same(dynamics, chunk.dynamicImports) || [...statics, ...dynamics].some(file => !known.has(file))) {
          throw new Error(`The CAD app could not account for the imports of ${name}: found ${[...statics]} / ${[...dynamics]}, recorded ${chunk.imports} / ${chunk.dynamicImports}`);
        }
        let code = edited.toString();
        if (original) {
          const map = remapping([edited.generateMap({ hires: true, source: name }), original], () => null);
          const stamped = stampDebugId(code, JSON.stringify({ ...map, file: name }), name);
          code = stamped.code;
          pairs.push({ name, code, map: stamped.map });
          ids[name] = stamped.debugId;
        }
        sources[name] = gzipSync(code, { level: 9 }).toString('base64');
        imports[name] = [...statics];
        if (chunk.isEntry) entry = name;
        delete bundle[chunk.fileName];
        delete bundle[mapName];
      }
      if (!entry) throw new Error('The CAD app build has no entry chunk.');
      const bootstrap = `const SOURCES=${JSON.stringify(sources)},IMPORTS=${JSON.stringify(imports)},IDS=${JSON.stringify(ids)},ENTRY=${JSON.stringify(entry)};\n${LOADER}`;
      document = document.replace(/<script\b[^>]*\bsrc="[^"]+"[^>]*><\/script>/, () => `<script type="module">${bootstrap}</script>`);
      for (const [name, item] of Object.entries(bundle)) {
        if (item.type === 'asset' && name.endsWith('.css')) {
          document = document.replace(/<link\b[^>]*\bhref="[^"]+\.css"[^>]*>/, () => `<style>${String(item.source).replace(/<\/style/gi, '<\\/style')}</style>`);
          delete bundle[name];
        }
      }
      // The workers' maps, inline or not: a worker's crash never reaches the page's reporter, and the page
      // loads no map.
      for (const name of Object.keys(bundle)) if (name.endsWith('.js.map')) delete bundle[name];
      const external = Object.keys(bundle).filter(name => name !== 'index.html');
      if (external.length) throw new Error(`Everything the CAD app loads must be inside index.html: ${external.join(', ')}`);
      const notices = drawingFiles.filter(file => file.fileName.includes('/licenses/')).map(file => `${file.fileName}\n${file.source}`).join('\n\n');
      html.source = document + `\n<!-- Bundled font licenses\n${notices.replaceAll('-->', '-- >')}\n-->`;
    } },
    // Each chunk as the page runs it, beside its map, for the release to upload: never inside the page.
    writeBundle(options) {
      const out = path.join(options.dir, 'sourcemaps');
      fs.rmSync(out, { recursive: true, force: true });
      fs.mkdirSync(out, { recursive: true });
      for (const { name, code, map } of pairs) {  // each chunk ends with its `//# debugId=`
        fs.writeFileSync(path.join(out, name), code);
        fs.writeFileSync(path.join(out, `${name}.map`), map);
      }
    },
  };
}

// Which build this is, for the version the app menu shows (src/App.tsx): none for the release's
// own, this checkout's commit for any other (@text-to-cad/ui/build-id).
const appRoot = fileURLToPath(new URL('.', import.meta.url));
const { version } = JSON.parse(fs.readFileSync(new URL('package.json', import.meta.url), 'utf8'));

export default defineConfig({
  define: { __TEXT_TO_CAD_BUILD__: JSON.stringify(buildId({ version, cwd: appRoot })) },
  plugins: [packageSourceMaps(['@text-to-cad/core', '@text-to-cad/ui']), inlineWorkers(), inlineDrawingFonts(), react(), inlineDocument()],
  resolve: { dedupe: ['react', 'react-dom', 'three', 'lucide-react'] },
  build: {
    assetsInlineLimit: Infinity, cssCodeSplit: false, modulePreload: false,
    sourcemap: 'hidden', rolldownOptions: { output: { sourcemapDebugIds: true } },
  },
  worker: { format: 'es', rolldownOptions: { output: { codeSplitting: false } } },
});
