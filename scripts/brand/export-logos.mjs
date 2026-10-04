// Raster exports and app copies of the logo vectors in apps/docs/public/brand,
// which are the source of truth. Next.js supplies sharp in the docs install.
import { readFile, writeFile, copyFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const require = createRequire(path.join(root, 'apps/docs/package.json'));
const sharp = require('sharp');
const publicDir = path.join(root, 'apps/docs/public');
const brand = path.join(publicDir, 'brand');
for (const name of ['logo-c', 'logo-cad', 'logo-texttocad', 'logo-texttocad-stacked']) {
  const source = await readFile(path.join(brand, `${name}.svg`));
  await sharp(source, { density: 600 }).resize(name === 'logo-c' ? { width: 512, height: 512, fit: 'contain', background: '#00000000' } : { height: 512 }).png().toFile(path.join(brand, `${name}.png`));
}
await copyFile(path.join(brand, 'logo-c.png'), path.join(publicDir, 'favicon.png'));
const sizes = [16, 32, 48, 64, 128, 256];
const pngs = await Promise.all(sizes.map(size => sharp(path.join(brand, 'logo-c.png')).resize(size, size).png().toBuffer()));
const header = Buffer.alloc(6 + sizes.length * 16);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
for (let i = 0; i < sizes.length; i++) {
  const entry = 6 + i * 16;
  header[entry] = header[entry + 1] = sizes[i] % 256;
  header.writeUInt16LE(1, entry + 4);
  header.writeUInt16LE(32, entry + 6);
  header.writeUInt32LE(pngs[i].length, entry + 8);
  header.writeUInt32LE(offset, entry + 12);
  offset += pngs[i].length;
}
await writeFile(path.join(publicDir, 'favicon.ico'), Buffer.concat([header, ...pngs]));
for (const file of ['favicon.png', 'favicon.ico']) {
  await copyFile(path.join(publicDir, file), path.join(root, 'apps/web/src/client/assets', file));
}
// The viewer's home page draws the TEXTTOCAD wordmark and its version menu the CAD one, both from
// the shared UI package; both plugin listings (Codex, and claude.ai's directory) use the C icon.
await copyFile(path.join(brand, 'logo-cad.svg'), path.join(root, 'packages/ui/src/assets/logo-cad.svg'));
await copyFile(path.join(brand, 'logo-texttocad.svg'), path.join(root, 'packages/ui/src/assets/logo-texttocad.svg'));
await copyFile(path.join(brand, 'logo-c.png'), path.join(root, '.codex-plugin/logo.png'));
await copyFile(path.join(brand, 'logo-c.png'), path.join(root, '.claude-plugin/icon.png'));
console.log('Exported C, CAD, TEXTTOCAD and stacked TEXT TO CAD PNGs, the favicons, the viewer wordmarks and the plugin icons.');
