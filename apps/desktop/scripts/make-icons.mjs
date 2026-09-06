/**
 * Writes `build/icon.png`, the one icon electron-builder needs: it derives the
 * `.icns` for macOS and the `.ico` for Windows from a square PNG of at least
 * 512×512, and Linux uses the PNG directly. One source file, no icon toolchain.
 *
 * The artwork is a placeholder — a rounded square with an H cut out of it —
 * drawn here in a few lines of pixel arithmetic rather than pulled in as a
 * binary blob, so it is reviewable and so replacing it later is a diff instead
 * of an upload. Run `npm run icons` after editing.
 *
 * The PNG is written by hand (one IDAT, filter type 0, zlib from node:zlib)
 * because adding an image library for a placeholder would be the tail wagging
 * the dog.
 */
import { deflateSync } from "node:zlib";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SIZE = 1024;
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const output = path.join(appRoot, "build", "icon.png");

// shadcn neutral, dark: the app's own --background and --foreground.
const BACKGROUND = [10, 10, 10, 255];
const FOREGROUND = [250, 250, 250, 255];
const TRANSPARENT = [0, 0, 0, 0];

/** macOS rounds app icons at roughly this fraction of the side. */
const CORNER_RADIUS = SIZE * 0.225;
/** Apple's icon grid leaves the artwork inset from the canvas. */
const INSET = SIZE * 0.06;

function insideRoundedSquare(x, y) {
  const left = INSET;
  const top = INSET;
  const right = SIZE - INSET;
  const bottom = SIZE - INSET;
  if (x < left || x > right || y < top || y > bottom) {
    return false;
  }
  const cx = Math.min(Math.max(x, left + CORNER_RADIUS), right - CORNER_RADIUS);
  const cy = Math.min(Math.max(y, top + CORNER_RADIUS), bottom - CORNER_RADIUS);
  return (x - cx) ** 2 + (y - cy) ** 2 <= CORNER_RADIUS ** 2;
}

/** An H: two uprights and a crossbar, in the middle third of the icon. */
function insideGlyph(x, y) {
  const stroke = SIZE * 0.085;
  const left = SIZE * 0.325;
  const right = SIZE * 0.675;
  const top = SIZE * 0.315;
  const bottom = SIZE * 0.685;
  if (y < top || y > bottom) {
    return false;
  }
  const onUpright =
    (x >= left && x <= left + stroke) || (x >= right - stroke && x <= right);
  const midpoint = (top + bottom) / 2;
  const onCrossbar =
    x >= left && x <= right && Math.abs(y - midpoint) <= stroke / 2;
  return onUpright || onCrossbar;
}

function pixels() {
  // One extra byte per row: PNG's per-scanline filter type, 0 = none.
  const raw = Buffer.alloc(SIZE * (SIZE * 4 + 1));
  let offset = 0;
  for (let y = 0; y < SIZE; y += 1) {
    raw[offset] = 0;
    offset += 1;
    for (let x = 0; x < SIZE; x += 1) {
      // +0.5 samples the centre of the pixel, which keeps the circle's edge
      // symmetric instead of biased a pixel up and left.
      const px = x + 0.5;
      const py = y + 0.5;
      const colour = !insideRoundedSquare(px, py)
        ? TRANSPARENT
        : insideGlyph(px, py)
          ? FOREGROUND
          : BACKGROUND;
      raw[offset] = colour[0];
      raw[offset + 1] = colour[1];
      raw[offset + 2] = colour[2];
      raw[offset + 3] = colour[3];
      offset += 4;
    }
  }
  return raw;
}

const CRC_TABLE = Array.from({ length: 256 }, (_unused, index) => {
  let c = index;
  for (let bit = 0; bit < 8; bit += 1) {
    c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  }
  return c >>> 0;
});

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

function png() {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(SIZE, 0);
  header.writeUInt32BE(SIZE, 4);
  header[8] = 8; // bit depth
  header[9] = 6; // colour type: truecolour with alpha
  header[10] = 0; // deflate
  header[11] = 0; // adaptive filtering
  header[12] = 0; // no interlace
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(pixels(), { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, png());
console.info(`wrote ${path.relative(appRoot, output)} (${SIZE}×${SIZE})`);
