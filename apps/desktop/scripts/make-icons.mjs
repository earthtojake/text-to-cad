/**
 * Writes the app's icon set: `build/icon.png` (1024², Linux and the fallback),
 * `build/icon.icns` (macOS) and `build/icon.ico` (Windows). Run `npm run icons`
 * after editing; the three files are committed because a packaging run must not
 * depend on a code path that could draw something different.
 *
 * The mark is an isometric cube — the smallest honest picture of what this app
 * is for — on the shadcn neutral field the rest of the UI uses. Drawn here in
 * pixel arithmetic rather than pulled in as a binary blob, so it is reviewable
 * and so changing it is a diff instead of an upload.
 *
 * Everything is written by hand from `node:zlib`: PNG (one IDAT, filter type 0),
 * ICNS (an 8-byte header per PNG member) and ICO (a directory of PNG members).
 * All three formats take PNG payloads, so one renderer feeds all of them, and
 * adding an image toolchain for nine small squares would be the tail wagging
 * the dog.
 */
import { deflateSync } from "node:zlib";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const buildDir = path.join(appRoot, "build");

/* -------------------------------------------------------------------------- */
/* The artwork                                                                 */
/* -------------------------------------------------------------------------- */

// shadcn neutral. The field is the app's own --background; the three faces are
// neutral 50 / 400 / 500, which is enough separation to read as a solid at
// 16 px and enough restraint not to fight the dock at 1024.
const FIELD = [10, 10, 10, 255];
const FACE_TOP = [250, 250, 250, 255];
const FACE_LEFT = [163, 163, 163, 255];
const FACE_RIGHT = [115, 115, 115, 255];
const TRANSPARENT = [0, 0, 0, 0];

/** macOS rounds app icons at roughly this fraction of the side. */
const CORNER_RADIUS = 0.225;
/** Apple's icon grid leaves the artwork inset from the canvas. */
const INSET = 0.06;
/** Half the cube's height, as a fraction of the side. */
const CUBE = 0.28;

/** Isometric projection of a unit cube's corner, in fractions of the side. */
function project(x, y, z) {
  return [(x - y) * Math.cos(Math.PI / 6) * CUBE, ((x + y) * 0.5 - z) * CUBE];
}

/** The three visible faces, each as a screen-space quad. */
const FACES = [
  // Top (z = 1), then the two vertical faces the viewer can see.
  { colour: FACE_TOP, corners: [[0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]] },
  { colour: FACE_LEFT, corners: [[0, 1, 0], [1, 1, 0], [1, 1, 1], [0, 1, 1]] },
  { colour: FACE_RIGHT, corners: [[1, 0, 0], [1, 1, 0], [1, 1, 1], [1, 0, 1]] },
].map((face) => ({
  colour: face.colour,
  // Corner order round the quad matters: the inside test below is a sign test
  // on the cross product of consecutive edges, which only holds for a convex
  // polygon wound consistently.
  points: orderQuad(face.corners.map(([x, y, z]) => project(x, y, z))),
}));

/** Wind four coplanar points into a convex quad (sort by angle about their mean). */
function orderQuad(points) {
  const cx = points.reduce((sum, [x]) => sum + x, 0) / points.length;
  const cy = points.reduce((sum, [, y]) => sum + y, 0) / points.length;
  return [...points].sort(
    (a, b) => Math.atan2(a[1] - cy, a[0] - cx) - Math.atan2(b[1] - cy, b[0] - cx),
  );
}

function insidePolygon(points, x, y) {
  let sign = 0;
  for (let index = 0; index < points.length; index += 1) {
    const [ax, ay] = points[index];
    const [bx, by] = points[(index + 1) % points.length];
    const cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax);
    if (cross === 0) {
      continue;
    }
    const next = cross > 0 ? 1 : -1;
    if (sign === 0) {
      sign = next;
    } else if (sign !== next) {
      return false;
    }
  }
  return true;
}

function insideRoundedSquare(x, y) {
  const left = INSET;
  const top = INSET;
  const right = 1 - INSET;
  const bottom = 1 - INSET;
  if (x < left || x > right || y < top || y > bottom) {
    return false;
  }
  const cx = Math.min(Math.max(x, left + CORNER_RADIUS), right - CORNER_RADIUS);
  const cy = Math.min(Math.max(y, top + CORNER_RADIUS), bottom - CORNER_RADIUS);
  return (x - cx) ** 2 + (y - cy) ** 2 <= CORNER_RADIUS ** 2;
}

/** The colour at one point, in unit coordinates with the origin top-left. */
function sample(x, y) {
  if (!insideRoundedSquare(x, y)) {
    return TRANSPARENT;
  }
  // Centred on the canvas, and lifted a hair: an isometric cube's optical
  // centre sits below its bounding box's.
  const dx = x - 0.5;
  const dy = y - 0.5 + CUBE * 0.02;
  for (const face of FACES) {
    if (insidePolygon(face.points, dx, dy)) {
      return face.colour;
    }
  }
  return FIELD;
}

/**
 * Render one square RGBA bitmap.
 *
 * Supersampled: the edges here are diagonals, and a diagonal without
 * antialiasing is a staircase at every size the dock actually draws. `samples`
 * per axis is enough at 1024 and cheap at 16.
 */
function bitmap(size, samples = 4) {
  // One extra byte per row: PNG's per-scanline filter type, 0 = none.
  const raw = Buffer.alloc(size * (size * 4 + 1));
  let offset = 0;
  for (let py = 0; py < size; py += 1) {
    raw[offset] = 0;
    offset += 1;
    for (let px = 0; px < size; px += 1) {
      let r = 0;
      let g = 0;
      let b = 0;
      let a = 0;
      for (let sy = 0; sy < samples; sy += 1) {
        for (let sx = 0; sx < samples; sx += 1) {
          const [sr, sg, sb, sa] = sample(
            (px + (sx + 0.5) / samples) / size,
            (py + (sy + 0.5) / samples) / size,
          );
          // Premultiplied: a sample outside the rounded square is fully
          // transparent black, so averaging straight RGB would drag the edge
          // pixels toward black instead of toward nothing.
          const alpha = sa / 255;
          r += sr * alpha;
          g += sg * alpha;
          b += sb * alpha;
          a += sa;
        }
      }
      const count = samples * samples;
      const alpha = a / count;
      const scale = alpha === 0 ? 0 : 255 / a;
      raw[offset] = Math.round(r * scale);
      raw[offset + 1] = Math.round(g * scale);
      raw[offset + 2] = Math.round(b * scale);
      raw[offset + 3] = Math.round(alpha);
      offset += 4;
    }
  }
  return raw;
}

/* -------------------------------------------------------------------------- */
/* PNG                                                                         */
/* -------------------------------------------------------------------------- */

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

function png(size) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8; // bit depth
  header[9] = 6; // colour type: truecolour with alpha
  header[10] = 0; // deflate
  header[11] = 0; // adaptive filtering
  header[12] = 0; // no interlace
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(bitmap(size), { level: 9 })),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

/* -------------------------------------------------------------------------- */
/* ICNS and ICO                                                                */
/* -------------------------------------------------------------------------- */

/**
 * macOS icon suite. Each member is an OSType, a big-endian length that counts
 * its own 8-byte header, and the payload — a PNG for every type listed here.
 * The `ic1x` types are the retina halves of the `ic0x` ones, which is why 256
 * and 512 appear twice: the same pixels, offered at two scale factors.
 */
const ICNS_TYPES = [
  ["icp4", 16],
  ["icp5", 32],
  ["ic07", 128],
  ["ic08", 256],
  ["ic09", 512],
  ["ic10", 1024],
  ["ic11", 32],
  ["ic12", 64],
  ["ic13", 256],
  ["ic14", 512],
];

function icns(pngs) {
  const members = ICNS_TYPES.map(([type, size]) => {
    const data = pngs.get(size);
    const header = Buffer.alloc(8);
    header.write(type, 0, "ascii");
    header.writeUInt32BE(data.length + 8, 4);
    return Buffer.concat([header, data]);
  });
  const body = Buffer.concat(members);
  const header = Buffer.alloc(8);
  header.write("icns", 0, "ascii");
  header.writeUInt32BE(body.length + 8, 4);
  return Buffer.concat([header, body]);
}

/** Windows icon. PNG members are valid from Vista on, which is every target. */
const ICO_SIZES = [16, 24, 32, 48, 64, 128, 256];

function ico(pngs) {
  const entries = ICO_SIZES.map((size) => pngs.get(size));
  const header = Buffer.alloc(6);
  header.writeUInt16LE(0, 0); // reserved
  header.writeUInt16LE(1, 2); // 1 = icon
  header.writeUInt16LE(entries.length, 4);

  const directory = Buffer.alloc(entries.length * 16);
  let offset = header.length + directory.length;
  entries.forEach((data, index) => {
    const at = index * 16;
    const size = ICO_SIZES[index];
    // 256 is written as 0: the field is one byte and 256 does not fit in it.
    directory[at] = size === 256 ? 0 : size;
    directory[at + 1] = size === 256 ? 0 : size;
    directory[at + 2] = 0; // palette size
    directory[at + 3] = 0; // reserved
    directory.writeUInt16LE(1, at + 4); // colour planes
    directory.writeUInt16LE(32, at + 6); // bits per pixel
    directory.writeUInt32LE(data.length, at + 8);
    directory.writeUInt32LE(offset, at + 12);
    offset += data.length;
  });

  return Buffer.concat([header, directory, ...entries]);
}

/* -------------------------------------------------------------------------- */

const sizes = [...new Set([...ICNS_TYPES.map(([, size]) => size), ...ICO_SIZES, 1024])].sort(
  (a, b) => a - b,
);
const pngs = new Map(sizes.map((size) => [size, png(size)]));

fs.mkdirSync(buildDir, { recursive: true });
const written = [
  ["icon.png", pngs.get(1024)],
  ["icon.icns", icns(pngs)],
  ["icon.ico", ico(pngs)],
];
for (const [name, data] of written) {
  fs.writeFileSync(path.join(buildDir, name), data);
  console.info(`wrote build/${name} (${(data.length / 1024).toFixed(1)} kB)`);
}
