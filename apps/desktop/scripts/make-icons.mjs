/**
 * Render the existing blue sidebar star onto a dark macOS-grid tile.
 * `build/icon.png` is shared by the development Dock icon and electron-builder,
 * which derives the packaged .icns and .ico from it. No redraw of the mark.
 *
 *   npm run icons
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(appRoot, "src", "renderer", "assets", "brand", "hardcore-star.svg");
const target = path.join(appRoot, "build", "icon.png");

const CANVAS_PX = 1024;

/** The tile's side as a fraction of the canvas — Apple's 824 of 1024. */
const TILE_FRACTION = 824 / 1024;

/** The tile's fill: the app's own background (`resources/brand`'s `INK`). */
const TILE_FILL = "#292929";

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
  console.error(`make-icons: sidebar star not found at ${source}`);
  process.exit(1);
}

const tile = Math.round(CANVAS_PX * TILE_FRACTION);
const inset = (CANVAS_PX - tile) / 2;
const mark = `data:image/svg+xml;base64,${fs.readFileSync(source).toString("base64")}`;
const markSize = Math.round(tile * 0.78);
const markInset = (tile - markSize) / 2;

const svg =
  `<svg id="icon" xmlns="http://www.w3.org/2000/svg" width="${CANVAS_PX}" height="${CANVAS_PX}"` +
  ` viewBox="0 0 ${CANVAS_PX} ${CANVAS_PX}">` +
  `<g transform="translate(${inset} ${inset})">` +
  `<path d="${squirclePath(tile)}" fill="${TILE_FILL}"/>` +
  `<image href="${mark}" x="${markInset}" y="${markInset}" width="${markSize}" height="${markSize}"/>` +
  `</g></svg>`;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: CANVAS_PX, height: CANVAS_PX } });
  await page.setContent(
    `<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:transparent}` +
      `svg{display:block}</style><body>${svg}</body>`,
  );
  // Decode the exact SVG image before capturing it; getBBox alone only checks layout.
  await page.evaluate(async (src) => {
    const img = new Image();
    img.src = src;
    await img.decode();
    await new Promise(requestAnimationFrame);
  }, mark);
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
