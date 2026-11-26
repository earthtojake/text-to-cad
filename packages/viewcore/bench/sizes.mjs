// viewcore.wasm sizes: raw, gzip -9, brotli (quality 11).   node sizes.mjs [path/to/viewcore.wasm]
import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";
import { fileURLToPath } from "node:url";

const file = process.argv[2] || path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "dist", "viewcore.wasm");
const raw = fs.readFileSync(file);
const gz = zlib.gzipSync(raw, { level: 9 });
const br = zlib.brotliCompressSync(raw, { params: { [zlib.constants.BROTLI_PARAM_QUALITY]: 11, [zlib.constants.BROTLI_PARAM_SIZE_HINT]: raw.length, [zlib.constants.BROTLI_PARAM_LGWIN]: 24 } });
const mb = (n) => (n / 2 ** 20).toFixed(2) + " MiB";
console.log(JSON.stringify({ file, raw: raw.length, gzip9: gz.length, brotli11: br.length }));
console.log(`raw     ${raw.length}  (${mb(raw.length)})\ngzip -9 ${gz.length}  (${mb(gz.length)})\nbrotli  ${br.length}  (${mb(br.length)})`);
