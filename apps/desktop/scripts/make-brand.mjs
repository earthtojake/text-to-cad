/**
 * Renders the Hardcore brand marks into `resources/brand/` (committed).
 *
 * The mark is the word HARDCORE — or the letter H alone — set in JetBrains Mono
 * ExtraBold Italic, drawn twice: a light-blue copy offset down and right, then
 * the foreground copy on top of it. No blur and no gradient; the "shadow" is a
 * second crisp copy of the same glyphs, so the mark survives being scaled,
 * printed or read at 16px.
 *
 * Everything is measured, nothing is eyeballed. The glyph ink box comes from
 * the canvas text metrics of the real face (`actualBoundingBox*`), so the
 * wordmark crops tight to the letters plus one margin, and the monogram sits
 * on the macOS icon grid rather than wherever the font's line box happened to
 * put it. The face is embedded as a data URL, so the render depends on the
 * committed woff2 and not on what is installed on the machine.
 *
 *   npm run brand
 *
 * Deterministic: same font, same Chromium, same bytes. `npm run icons` reads
 * `hardcore-h.png` from here, so run this first when the mark changes.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const brandDir = path.join(appRoot, "resources", "brand");
const fontFile = path.join(brandDir, "fonts", "JetBrainsMono-ExtraBoldItalic.woff2");

/**
 * The palette.
 *
 * `BLUE` is the app icon's own blue, so the wordmark and the icon are the same
 * mark. The icon (`apps/docs/public/favicon.png`, which `make-icons.mjs` drew
 * from until this script existed) is a shaded 3D render and therefore has no
 * single hex: this is the mean of its opaque, unambiguously blue pixels
 * (b - r > 40) in the light luminance band (0.2126r + 0.7152g + 0.0722b
 * between 150 and 190) — the star's lit faces, 16874 pixels of the 512x512.
 * The bands either side of it are #3e90ce (mid) and #a3e2fd (highlights).
 */
const BLUE = "#62b7ec";
const INK = "#0a0a0a"; // the app's background, and the wordmark's ink on light
const PAPER = "#ffffff";

/**
 * How far the blue copy is offset, as a fraction of the CAP HEIGHT — not of the
 * font size, because cap height is what the eye measures the offset against.
 * Right and down by the same amount, so the light reads as coming from the top
 * left. 0.09 is the smallest offset that still separates the two copies at the
 * weight of the H's stem; below ~0.06 the blue disappears under the ink.
 */
const SHADOW_OFFSET_CAP_FRACTION = 0.09;

/** JetBrains Mono's cap height, from the face's OS/2 sCapHeight (1000 upem). */
const CAP_HEIGHT_EM = 0.73;

/** The wordmark's type size in CSS pixels at 1x. */
const WORDMARK_FONT_PX = 200;

/** The margin around the wordmark's ink, as a fraction of the type size. */
const WORDMARK_MARGIN_FRACTION = 0.08;

/** The monogram is a square this many pixels on a side. */
const MONOGRAM_PX = 1024;

/**
 * The monogram's ink box — both copies together — fills this much of its
 * square, on the taller of its two axes.
 *
 * This number is also the icon's, because `make-icons.mjs` draws this whole
 * square onto the icon's tile: whatever share of the square the ink takes, it
 * takes of the tile, with no second scale factor to keep in step. 0.72 puts it
 * inside the inner 80% macOS's icon grid asks for and leaves the H's arms clear
 * of where the tile's corners start to curve; at 0.80 exactly the bottom-left
 * foot crowds the corner and the icon reads a size larger than its neighbours.
 */
const MONOGRAM_INK_FRACTION = 0.72;

const fontDataUrl = `data:font/woff2;base64,${fs.readFileSync(fontFile).toString("base64")}`;

/**
 * The page every mark is drawn into. One @font-face, and an SVG per mark: SVG
 * `<text>` takes an explicit baseline, which a div does not, and a baseline is
 * the only way to place ink where the metrics say it should go.
 */
const pageHtml = `<!doctype html>
<meta charset="utf-8">
<style>
  @font-face {
    font-family: "HardcoreBrand";
    src: url("${fontDataUrl}") format("woff2");
    font-weight: 800;
    font-style: italic;
    font-display: block;
  }
  html, body { margin: 0; padding: 0; background: transparent; }
  svg { display: block; }
  text {
    font-family: "HardcoreBrand";
    font-weight: 800;
    font-style: italic;
    white-space: pre;
  }
</style>
<body></body>`;

/**
 * The ink box of `text` at `fontPx`, in CSS pixels, from the face itself.
 * `left`/`right` are measured from the alignment point, `ascent`/`descent`
 * from the baseline — so the caller places the baseline, not the line box.
 */
function measureInk(page, text, fontPx) {
  return page.evaluate(
    ({ text, fontPx }) => {
      const ctx = document.createElement("canvas").getContext("2d");
      ctx.font = `italic 800 ${fontPx}px HardcoreBrand`;
      ctx.textBaseline = "alphabetic";
      const m = ctx.measureText(text);
      return {
        left: m.actualBoundingBoxLeft,
        right: m.actualBoundingBoxRight,
        ascent: m.actualBoundingBoxAscent,
        descent: m.actualBoundingBoxDescent,
      };
    },
    { text, fontPx },
  );
}

/** The two copies: blue first, then the foreground on top. */
function markLayers({ text, fontPx, x, baseline, offset, fg }) {
  const esc = text.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  const at = (dx, dy, fill) =>
    `<text x="${x + dx}" y="${baseline + dy}" font-size="${fontPx}" fill="${fill}">${esc}</text>`;
  return `${at(offset, offset, BLUE)}${at(0, 0, fg)}`;
}

async function renderSvg(page, { width, height, body, outFile }) {
  await page.setViewportSize({ width: Math.ceil(width), height: Math.ceil(height) });
  await page.evaluate(
    ({ width, height, body }) => {
      document.body.innerHTML =
        `<svg id="mark" xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"` +
        ` viewBox="0 0 ${width} ${height}">${body}</svg>`;
    },
    { width, height, body },
  );
  await page.evaluate(() => document.fonts.ready);
  // `scale: "device"` is what makes the @2x pass 2x pixels rather than 2x
  // upscaled CSS pixels: the page's deviceScaleFactor does the work.
  const buffer = await page.locator("#mark").screenshot({ omitBackground: true, scale: "device" });
  fs.writeFileSync(outFile, buffer);
}

async function main() {
  fs.mkdirSync(brandDir, { recursive: true });
  const browser = await chromium.launch();
  const written = [];
  const contexts = [];
  try {
    // One context per device scale factor. Geometry is measured once, on the 1x
    // page, and reused: the @2x files are the same mark at twice the pixels,
    // not a second layout that happens to look similar.
    const openPage = async (deviceScaleFactor) => {
      const context = await browser.newContext({ deviceScaleFactor });
      contexts.push(context);
      const p = await context.newPage();
      await p.setContent(pageHtml);
      await p.evaluate(() => document.fonts.load('italic 800 100px "HardcoreBrand"'));
      await p.evaluate(() => document.fonts.ready);
      return p;
    };
    const page = await openPage(1);
    const page2x = await openPage(2);

    // ---- the wordmark ----
    const capPx = WORDMARK_FONT_PX * CAP_HEIGHT_EM;
    const offset = capPx * SHADOW_OFFSET_CAP_FRACTION;
    const margin = WORDMARK_MARGIN_FRACTION * WORDMARK_FONT_PX;
    const ink = await measureInk(page, "HARDCORE", WORDMARK_FONT_PX);
    const width = Math.ceil(ink.left + ink.right + offset + margin * 2);
    const height = Math.ceil(ink.ascent + ink.descent + offset + margin * 2);
    const wordmark = {
      text: "HARDCORE",
      fontPx: WORDMARK_FONT_PX,
      x: margin + ink.left,
      baseline: margin + ink.ascent,
      offset,
    };

    for (const [variant, fg] of [
      ["dark", PAPER],
      ["light", INK],
    ]) {
      for (const [scale, target] of [
        [1, page],
        [2, page2x],
      ]) {
        const suffix = scale === 2 ? "@2x" : "";
        const outFile = path.join(brandDir, `hardcore-wordmark-${variant}${suffix}.png`);
        await renderSvg(target, { width, height, outFile, body: markLayers({ ...wordmark, fg }) });
        written.push([outFile, `${width * scale}x${height * scale}`]);
      }
    }

    // ---- the H monogram ----
    // Fit the ink box of BOTH copies into MONOGRAM_INK_FRACTION of the square,
    // then centre that box. The H is measured at a probe size and scaled, so
    // the fit is exact rather than tuned.
    const probePx = 1000;
    const probe = await measureInk(page, "H", probePx);
    const probeOffset = probePx * CAP_HEIGHT_EM * SHADOW_OFFSET_CAP_FRACTION;
    const probeW = probe.left + probe.right + probeOffset;
    const probeH = probe.ascent + probe.descent + probeOffset;
    const targetInkPx = MONOGRAM_PX * MONOGRAM_INK_FRACTION;
    const monoFontPx = (probePx * targetInkPx) / Math.max(probeW, probeH);
    const monoOffset = monoFontPx * CAP_HEIGHT_EM * SHADOW_OFFSET_CAP_FRACTION;
    const scaleFromProbe = monoFontPx / probePx;
    const inkW = probeW * scaleFromProbe;
    const inkH = probeH * scaleFromProbe;
    const monogram = {
      text: "H",
      fontPx: monoFontPx,
      x: (MONOGRAM_PX - inkW) / 2 + probe.left * scaleFromProbe,
      baseline: (MONOGRAM_PX - inkH) / 2 + probe.ascent * scaleFromProbe,
      offset: monoOffset,
    };

    const square = { width: MONOGRAM_PX, height: MONOGRAM_PX };
    const transparent = path.join(brandDir, "hardcore-h.png");
    await renderSvg(page, {
      ...square,
      outFile: transparent,
      body: markLayers({ ...monogram, fg: PAPER }),
    });
    written.push([transparent, `${MONOGRAM_PX}x${MONOGRAM_PX}`]);

    for (const [variant, bg, fg] of [
      ["dark", INK, PAPER],
      ["light", PAPER, INK],
    ]) {
      const outFile = path.join(brandDir, `hardcore-h-${variant}.png`);
      await renderSvg(page, {
        ...square,
        outFile,
        body:
          `<rect width="${MONOGRAM_PX}" height="${MONOGRAM_PX}" fill="${bg}"/>` +
          markLayers({ ...monogram, fg }),
      });
      written.push([outFile, `${MONOGRAM_PX}x${MONOGRAM_PX}`]);
    }

    console.log(
      `make-brand: JetBrains Mono ExtraBold Italic, blue ${BLUE}, ` +
        `offset ${offset.toFixed(1)}px at ${WORDMARK_FONT_PX}px ` +
        `(${SHADOW_OFFSET_CAP_FRACTION * 100}% of cap height)`,
    );
    for (const [file, size] of written) {
      console.log(`make-brand: wrote ${path.relative(appRoot, file)} (${size})`);
    }
  } finally {
    for (const context of contexts) await context.close();
    await browser.close();
  }
}

await main();
