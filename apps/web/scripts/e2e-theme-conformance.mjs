#!/usr/bin/env node
// Does a theme actually reach the pixels?
//
// The viewer has ONE theme and one renderer behind it: the mesh path (three.js materials
// and lights). A theme owns both the shared stage and the model's own surface, and the
// capability table in viewer/docs/render-types.md declares what each render type honours.
//
// So this asserts: SURFACE RESPONSE, recorded — the model's own pixels must CHANGE when
// the theme changes. A renderer that ignores a theme still starts up and still draws,
// while looking identical in all eight themes, which is precisely the failure this exists
// to catch: `lighting.fill` and `lighting.rim` were once dropped at normalization and
// every theme rendered with the same rig.
//
// Usage:
//   node viewer/scripts/e2e-theme-conformance.mjs --dir <models-root> [--url http://127.0.0.1:3245]
//                                                 [--out <dir>] [--baseline <file>]
//
// Requires a viewer already serving <models-root> (npm run start) and
// playwright available. Exits non-zero on a parity failure or an unresponsive surface.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

// Every shipped preset. The custom slot is deliberately excluded: it is whatever the user
// last edited, so it is not a fixture.
const THEME_IDS = [
  "workbench-light",
  "workbench-dark",
  "cinematic",
  "vibrant",
  "blue",
  "pink",
  "clay-sunrise",
  "terminal"
];

// One scene per RENDERER, not per format. The mesh fixture is an STL because it loads with
// no build step, so a theme sweep does not spend eight package rebuilds proving a point
// about lighting.
const SCENES = [
  { renderer: "mesh", file: "fun/miniature_spiral_staircase_highres.stl" }
];

const THEME_STORAGE_KEY = "cad-viewer:theme";
// Must match THEME_STORAGE_VERSION in viewer/src/client/workbench/persistence.js. A stale
// version is ignored on read, which would silently run all eight passes on the default
// theme and report perfect parity.
const THEME_STORAGE_VERSION = 12;

const VIEWPORT = { width: 1440, height: 900 };
// Top-left of the viewport: stage backdrop under every fixture, clear of the toolbar, the
// file sheet and the model itself.
const BACKGROUND_CLIP = { x: 24, y: 120, width: 160, height: 160 };
// The middle band, where each fixture's geometry actually sits.
const SURFACE_CLIP = { x: 260, y: 240, width: 520, height: 420 };

function parseArgs(argv) {
  const args = { url: "http://127.0.0.1:3245", dir: "", out: "", baseline: "" };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--url") args.url = argv[++index] || args.url;
    else if (flag === "--dir") args.dir = argv[++index] || "";
    else if (flag === "--out") args.out = argv[++index] || "";
    else if (flag === "--baseline") args.baseline = argv[++index] || "";
  }
  return args;
}

function meanRgb(png) {
  let r = 0;
  let g = 0;
  let b = 0;
  let n = 0;
  for (let index = 0; index < png.data.length; index += 4) {
    r += png.data[index];
    g += png.data[index + 1];
    b += png.data[index + 2];
    n += 1;
  }
  return n ? [r / n, g / n, b / n] : [0, 0, 0];
}

function rgbDistance(a, b) {
  return Math.max(Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1]), Math.abs(a[2] - b[2]));
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args.dir) {
    console.error("--dir <models-root> is required (absolute path the viewer is serving)");
    process.exit(2);
  }
  const modelsRoot = path.resolve(args.dir);
  // The URL no longer names the directory, so a viewer launched from the wrong directory would
  // just render nothing after a 9s wait per scene. Fail here instead, on the same paths
  // the viewer will be asked for.
  const missing = SCENES.map(({ file }) => file).filter((file) => !fs.existsSync(path.join(modelsRoot, file)));
  if (missing.length) {
    console.error(`scenes missing under ${modelsRoot} (is the viewer serving this root?):`);
    for (const file of missing) console.error(`  ${file}`);
    process.exit(2);
  }
  const { chromium } = require("playwright");
  const { PNG } = require("pngjs");

  const browser = await chromium.launch({ args: ["--use-angle=metal", "--ignore-gpu-blocklist"] });
  const results = [];

  for (const scene of SCENES) {
    for (const themeId of THEME_IDS) {
      // A fresh context per pass: the theme is read from localStorage at boot, so it has to
      // be seeded before the first paint rather than toggled afterwards.
      const context = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: 1 });
      await context.addInitScript(([key, version, id]) => {
        window.localStorage.setItem(key, JSON.stringify({ version, themeId: id, custom: null }));
      }, [THEME_STORAGE_KEY, THEME_STORAGE_VERSION, themeId]);
      const page = await context.newPage();
      const errors = [];
      page.on("pageerror", (error) => errors.push(String(error).slice(0, 160)));

      // The viewer under test must already be serving modelsRoot (its launch cwd).
      const url = `${args.url}?file=${encodeURIComponent(scene.file)}`;
      await page.goto(url, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(9000);

      const activeThemeId = await page.evaluate((key) => {
        try {
          return JSON.parse(window.localStorage.getItem(key) || "{}").themeId || "";
        } catch {
          return "";
        }
      }, THEME_STORAGE_KEY);

      const backgroundPng = PNG.sync.read(await page.screenshot({ clip: BACKGROUND_CLIP }));
      const surfacePng = PNG.sync.read(await page.screenshot({ clip: SURFACE_CLIP }));
      if (args.out) {
        fs.mkdirSync(args.out, { recursive: true });
        fs.writeFileSync(
          path.join(args.out, `${scene.renderer}-${themeId}.png`),
          await page.screenshot({ clip: SURFACE_CLIP })
        );
      }

      results.push({
        renderer: scene.renderer,
        themeId,
        activeThemeId,
        background: meanRgb(backgroundPng).map((value) => Number(value.toFixed(2))),
        surface: meanRgb(surfacePng).map((value) => Number(value.toFixed(2))),
        errors: errors.slice(0, 2)
      });
      await context.close();
    }
  }

  await browser.close();

  const failures = [];
  for (const result of results) {
    if (result.activeThemeId && result.activeThemeId !== result.themeId) {
      failures.push(`${result.renderer}/${result.themeId}: viewer ran theme ${result.activeThemeId}`);
    }
    for (const error of result.errors) {
      failures.push(`${result.renderer}/${result.themeId}: page error ${error}`);
    }
  }

  // Surface response: each renderer must actually look different across themes.
  console.log("surface response across themes (must not be flat):");
  for (const scene of SCENES) {
    const passes = results.filter((result) => result.renderer === scene.renderer);
    let spread = 0;
    for (const a of passes) {
      for (const b of passes) spread = Math.max(spread, rgbDistance(a.surface, b.surface));
    }
    const ok = spread > 4;
    if (!ok) failures.push(`${scene.renderer}: surface is identical across all themes (spread ${spread.toFixed(1)}/255)`);
    console.log(`  ${ok ? "ok  " : "FAIL"} ${scene.renderer.padEnd(9)} spread=${spread.toFixed(1)}/255`);
    for (const pass of passes) console.log(`         ${pass.themeId.padEnd(16)} ${pass.surface}`);
  }

  if (args.baseline) {
    fs.mkdirSync(path.dirname(path.resolve(args.baseline)), { recursive: true });
    fs.writeFileSync(path.resolve(args.baseline), `${JSON.stringify(results, null, 2)}\n`);
    console.log(`\nbaseline written to ${args.baseline}`);
  }

  if (failures.length) {
    console.log("\nfailures:");
    for (const failure of failures) console.log(`  ${failure}`);
  } else {
    console.log("\nevery theme reaches the surface");
  }
  process.exit(failures.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
