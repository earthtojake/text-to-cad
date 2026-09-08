/**
 * Writes `build/icon.png`, the app's one icon source, from the brand monogram
 * (`resources/brand/hardcore-h.png`, written by `npm run brand`): the H in
 * JetBrains Mono ExtraBold Italic with its light-blue offset copy, centred on a
 * dark tile.
 *
 * electron-builder derives the macOS `.icns` and the Windows `.ico` from this
 * one PNG at package time, and `src/main/index.ts` reads the same file as the
 * Dock icon when the app is unpackaged (`DEV_ICON`) — so `build/icon.png` is
 * the whole output. Nothing else is generated or committed.
 *
 * The geometry is macOS's icon grid, because that is the strictest of the three
 * and a mark drawn for it is not wrong anywhere else: a 1024px canvas with the
 * tile 824px of it (`TILE_FRACTION`). The glyph needs no sizing here — the
 * monogram's square is a known share of ink by construction
 * (`MONOGRAM_INK_FRACTION` in `make-brand.mjs`, 0.72, inside the inner 80% the
 * grid asks for), so drawing that square at the tile's size carries the share
 * over unchanged and there is no second scale factor to keep in step. The
 * transparent border is not waste: it is the room macOS expects around an app
 * icon, and an icon that fills its canvas sits visibly larger than its
 * neighbours in the Dock.
 *
 *   npm run brand && npm run icons
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(appRoot, "resources", "brand", "hardcore-h.png");
const target = path.join(appRoot, "build", "icon.png");

const CANVAS_PX = 1024;

/** The tile's side as a fraction of the canvas — Apple's 824 of 1024. */
const TILE_FRACTION = 824 / 1024;

/** The tile's fill: the app's own background (`resources/brand`'s `INK`). */
const TILE_FILL = "#0a0a0a";

/**
 * A superellipse — |x/a|^n + |y/a|^n = 1 — sampled as an SVG path. macOS's icon
 * corner is a continuous curve, not a circular arc, so a `border-radius`
 * rounded square reads subtly wrong beside its neighbours; n = 5 is close to
 * Apple's shape. A fixed sample count, so the path is identical every run.
 */
function squirclePath(size, n = 5, samples = 256) {
  const a = size / 2;
  const points = [];
  for (let i = 0; i < samples; i += 1) {
    const t = (i / samples) * Math.PI * 2;
    const cos = Math.cos(t);
    const sin = Math.sin(t);
    const x = Math.sign(cos) * a * Math.abs(cos) ** (2 / n);
    const y = Math.sign(sin) * a * Math.abs(sin) ** (2 / n);
    points.push(`${(a + x).toFixed(3)},${(a + y).toFixed(3)}`);
  }
  return `M${points.join("L")}Z`;
}

if (!fs.existsSync(source)) {
  console.error(`make-icons: brand monogram not found at ${source} — run \`npm run brand\` first`);
  process.exit(1);
}

const tile = Math.round(CANVAS_PX * TILE_FRACTION);
const inset = (CANVAS_PX - tile) / 2;
const monogram = `data:image/png;base64,${fs.readFileSync(source).toString("base64")}`;

const svg =
  `<svg id="icon" xmlns="http://www.w3.org/2000/svg" width="${CANVAS_PX}" height="${CANVAS_PX}"` +
  ` viewBox="0 0 ${CANVAS_PX} ${CANVAS_PX}">` +
  `<g transform="translate(${inset} ${inset})">` +
  `<path d="${squirclePath(tile)}" fill="${TILE_FILL}"/>` +
  `<image href="${monogram}" x="0" y="0" width="${tile}" height="${tile}"/>` +
  `</g></svg>`;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: CANVAS_PX, height: CANVAS_PX } });
  await page.setContent(
    `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:transparent}` +
      `svg{display:block}</style><body>${svg}</body>`,
  );
  // The monogram is an <image> href, not a document resource, so `load` says
  // nothing about it: wait for the decode before the shutter.
  await page.waitForFunction(() => {
    const img = document.querySelector("image");
    return img instanceof SVGImageElement && img.getBBox().width > 0;
  });
  await page.evaluate(() => document.fonts.ready);
  const buffer = await page.locator("#icon").screenshot({ omitBackground: true, scale: "device" });
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, buffer);
} finally {
  await browser.close();
}

console.log(
  `make-icons: wrote ${path.relative(appRoot, target)} (${CANVAS_PX}x${CANVAS_PX}, ` +
    `${tile}px tile) from ${path.relative(appRoot, source)}`,
);
