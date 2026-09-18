import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { describe, expect, it } from 'vitest';
import { pdfAssetFiles, pdfAssetsPlugin } from '../../../scripts/pdf-assets.mjs';
const require = createRequire(import.meta.url);
type Asset = { fileName: string; source: Buffer };
type Middleware = (request: { url: string }, response: {
  setHeader(name: string, value: string): void;
  end(value: Buffer): void;
}, next: () => void) => void;
describe('offline PDF assets', () => {
  it('ships encodings, codecs, profiles and compatible fonts with upstream notices', () => {
    const files = new Map(pdfAssetFiles().map(file => [file.fileName, file.source]));
    for (const name of ['cmaps/UniJIS-UTF16-H.bcmap', 'standard_fonts/FoxitSymbol.pfb', 'wasm/openjpeg.wasm', 'wasm/jbig2.wasm', 'wasm/qcms_bg.wasm', 'iccs/CGATS001Compat-v2-micro.icc', 'cmaps/LICENSE', 'wasm/LICENSE_OPENJPEG', 'standard_fonts/LICENSE_FOXIT', 'iccs/LICENSE']) expect(files.has(`pdfjs/${name}`), name).toBe(true);
    expect(files.get('pdfjs/standard_fonts/LICENSE_LIBERATION_OFL')?.toString()).toContain('SIL OPEN FONT LICENSE');
    expect(files.has('pdfjs/standard_fonts/LICENSE_LIBERATION')).toBe(false);
    const replacement = path.dirname(require.resolve('@betteroffice/fonts/package.json'));
    for (const style of ['Regular', 'Bold', 'Italic', 'BoldItalic']) expect(files.get(`pdfjs/standard_fonts/LiberationSans-${style}.ttf`)).toEqual(fs.readFileSync(path.join(replacement, `assets/LiberationSans-${style}.ttf`)));
  });
  it('serves exactly the same local assets in development and production', () => {
    const plugin = pdfAssetsPlugin(); const emitted: Asset[] = [];
    const generateBundle = plugin.generateBundle as unknown as (this: { emitFile(file: Asset): void }) => void;
    generateBundle.call({ emitFile: file => emitted.push(file) });
    let middleware: Middleware;
    const configureServer = plugin.configureServer as (server: { middlewares: { use(handler: Middleware): void } }) => void;
    configureServer({ middlewares: { use: handler => { middleware = handler; } } });
    for (const file of emitted) {
      let body: unknown; middleware!({ url: `/${file.fileName}` }, { setHeader() {}, end(value: Buffer) { body = value; } }, () => { throw new Error('asset missing'); });
      expect(body).toEqual(file.source);
    }
    let passed = false; middleware!({ url: '/pdfjs/../secret' }, { setHeader() {}, end() {} }, () => { passed = true; }); expect(passed).toBe(true);
  });
});
