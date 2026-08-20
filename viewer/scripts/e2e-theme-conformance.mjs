#!/usr/bin/env node
// Does a theme mean the same thing to every render type?
//
// The viewer has ONE theme and two renderers behind it: the mesh path (three.js materials
// and lights) and the implicit path (a raymarched SDF with a hand-written rig). They share
// the stage, so the parts of a theme that belong to the stage MUST agree pixel for pixel;
// the parts that belong to the surface can differ, but only in ways declared in the
// capability table in viewer/docs/render-types.md.
//
// So this asserts two different things:
//
//   1. BACKGROUND PARITY, hard: the same theme must produce the same backdrop pixel under
//      every render type. Any drift here is a bug — the backdrop is shared code.
//   2. SURFACE RESPONSE, recorded: the model's own pixels must CHANGE when the theme
//      changes. A renderer that ignores a theme still passes a background check while
//      looking identical in all eight themes, which is precisely the failure this exists
//      to catch: `lighting.fill` and `lighting.rim` were dropped at normalization and the
//      raymarcher rendered every theme with the same rig.
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

// One scene per RENDERER, not per format — the point of comparison is mesh vs raymarch.
// The mesh fixture is an STL because it loads with no build step, so a theme sweep does not
// spend eight package rebuilds proving a point about lighting.
const SCENES = [
  { renderer: "mesh", file: "fun/miniature_spiral_staircase_highres.stl" },
  { renderer: "implicit", file: "implicits/rounded-orb.implicit.js" }
];

// Background parity budget, per theme, in 0-255 channel distance. The backdrop is shared
// code, so the target is 0 and the default budget is rounding noise.
//
// Four themes carry a MEASURED, PRE-EXISTING drift (this harness is what found it; the
// numbers below are from the run that introduced it, and they are unchanged by the U4
// lighting work — verified by A/B). It is not the shader's own backdrop: in the viewer the
// raymarch pass composites over the shared stage, and swapping the shader's gradient ramp
// moved these numbers by 0.0. It is not the environment map either: forcing
// `environment.enabled = false` on cinematic leaves the delta at 7.1. Cause still unknown.
//
// Budgeted rather than ignored, so the drift cannot grow and cannot spread to a theme that
// is currently clean. Ratchet these down as they are fixed; never up.
const BACKGROUND_PARITY_DEFAULT_BUDGET = 2;
const BACKGROUND_PARITY_BUDGETS = {
  cinematic: 7.5,
  blue: 5,
  pink: 5.2,
  "clay-sunrise": 6
};

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

      const url = `${args.url}${modelsRoot}?dir=${encodeURIComponent(modelsRoot)}` +
        `&file=${encodeURIComponent(scene.file)}`;
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
  const byTheme = new Map();
  for (const result of results) {
    if (!byTheme.has(result.themeId)) byTheme.set(result.themeId, []);
    byTheme.get(result.themeId).push(result);
    if (result.activeThemeId && result.activeThemeId !== result.themeId) {
      failures.push(`${result.renderer}/${result.themeId}: viewer ran theme ${result.activeThemeId}`);
    }
    for (const error of result.errors) {
      failures.push(`${result.renderer}/${result.themeId}: page error ${error}`);
    }
  }

  // 1. Background parity across renderers, per theme.
  console.log("background parity (mesh vs implicit, per theme):");
  for (const [themeId, passes] of byTheme) {
    const mesh = passes.find((pass) => pass.renderer === "mesh");
    const implicit = passes.find((pass) => pass.renderer === "implicit");
    if (!mesh || !implicit) continue;
    const delta = rgbDistance(mesh.background, implicit.background);
    const budget = BACKGROUND_PARITY_BUDGETS[themeId] ?? BACKGROUND_PARITY_DEFAULT_BUDGET;
    const budgeted = themeId in BACKGROUND_PARITY_BUDGETS;
    const ok = delta <= budget;
    if (!ok) {
      failures.push(`${themeId}: background differs by ${delta.toFixed(1)}/255 between renderers (budget ${budget})`);
    } else if (budgeted && delta <= budget - 1.5) {
      // Same rule as the identity-check ratchet: a budget nobody is near stops ratcheting.
      failures.push(`${themeId}: background drift improved to ${delta.toFixed(1)} — lower its budget from ${budget}`);
    }
    const status = ok ? (budgeted ? "known" : "ok  ") : "FAIL";
    console.log(`  ${status} ${themeId.padEnd(16)} mesh=${mesh.background} implicit=${implicit.background} delta=${delta.toFixed(1)}${budgeted ? ` (budget ${budget})` : ""}`);
  }

  // 2. Surface response: each renderer must actually look different across themes.
  console.log("\nsurface response across themes (must not be flat):");
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
    console.log("\nevery theme means the same stage and a different surface, in both renderers");
  }
  process.exit(failures.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
