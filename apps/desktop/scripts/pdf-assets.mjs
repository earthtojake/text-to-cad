/** PDF.js supplemental assets are always local, for development and packaged apps. */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
export function pdfAssetFiles() {
  const root = path.dirname(require.resolve('pdfjs-dist/package.json'));
  if (JSON.parse(fs.readFileSync(path.join(root, 'package.json'), 'utf8')).version !== '6.3.289') throw new Error('Review PDF.js assets and licenses before upgrading');
  const replacement = path.dirname(require.resolve('@betteroffice/fonts/package.json'));
  if (JSON.parse(fs.readFileSync(path.join(replacement, 'package.json'), 'utf8')).version !== '0.2.0') throw new Error('Review PDF font replacements before upgrading');
  const files = [{ fileName: 'pdfjs/LICENSE', source: fs.readFileSync(path.join(root, 'LICENSE')) }];
  for (const directory of ['cmaps', 'standard_fonts', 'wasm', 'iccs']) {
    for (const entry of fs.readdirSync(path.join(root, directory), { withFileTypes: true })) {
      if (!entry.isFile()) throw new Error(`Unexpected PDF asset directory: ${entry.name}`);
      if (entry.name === 'LICENSE_LIBERATION') continue;
      const origin = directory === 'standard_fonts' && /^LiberationSans-.*\.ttf$/.test(entry.name)
        ? path.join(replacement, 'assets', entry.name) : path.join(root, directory, entry.name);
      files.push({ fileName: `pdfjs/${directory}/${entry.name}`, source: fs.readFileSync(origin) });
    }
  }
  files.push({ fileName: 'pdfjs/standard_fonts/LICENSE_LIBERATION_OFL', source: fs.readFileSync(path.join(replacement, 'LICENSES/OFL-Liberation.txt')) });
  return files;
}
/** @returns {import('vite').Plugin} */
export function pdfAssetsPlugin() {
  return {
    name: 'hardcore-offline-pdf-assets',
    configureServer(server) {
      const files = new Map(pdfAssetFiles().map(file => [`/${file.fileName}`, file]));
      server.middlewares.use((request, response, next) => {
        const file = files.get(new URL(request.url ?? '/', 'http://localhost').pathname);
        if (!file) return next();
        response.setHeader('Content-Type', file.fileName.endsWith('.wasm') ? 'application/wasm' : file.fileName.endsWith('.js') ? 'application/javascript' : 'application/octet-stream');
        response.end(file.source);
      });
    },
    generateBundle() { for (const file of pdfAssetFiles()) this.emitFile({ type: 'asset', ...file }); },
  };
}
