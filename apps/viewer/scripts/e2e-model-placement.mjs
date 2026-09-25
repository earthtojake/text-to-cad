#!/usr/bin/env node
// True-pose placement conformance: a model renders at its AUTHORED world
// coordinates in every theme — never re-centered on its bounds — and the
// reference grid obeys the floor coupling (followModel is a floor-dependent
// trait; with the stage floor disabled the grid is pinned to world z=0).
//
// Asserted through the read-only window.__cadModelPlacement seam CadViewer
// publishes when it places a model:
//
//   1. model group position is exactly (0,0,0) in EVERY theme;
//   2. the authored bounds reach the page unchanged (the demo plate is an
//      origin-centered Box(60,40,4): authored z=[-2,2], top face at z=2);
//   3. workbench light/dark (floor off): gridFloorZ === 0 and
//      floorFollowsModel === false;
//   4. cinematic (floor on): followModel may act — the grounded plate still
//      yields gridFloorZ === 0 (follow is downward-only).
//
// Usage:
//   node viewer/scripts/e2e-model-placement.mjs --dir <models-root>
//        [--url http://127.0.0.1:3245] [--file projects/demo-plate/STEP/plate.step]
//        [--out <dir>]
//
// Requires a viewer already serving <models-root> and playwright available.
// Exits non-zero on any violation.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

// Must match viewer/src/client (persistence): same key/version the theme
// conformance e2e uses.
const THEME_STORAGE_KEY = "cad-viewer:theme";
const THEME_STORAGE_VERSION = 12;

const EXPECTATIONS = [
  { themeId: "workbench-light", floorEnabled: false },
  { themeId: "workbench-dark", floorEnabled: false },
  { themeId: "cinematic", floorEnabled: true }
];

function parseArgs(argv) {
  const args = { url: "http://127.0.0.1:3245", file: "projects/demo-plate/STEP/plate.step" };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) continue;
    const next = argv[index + 1];
    args[token.slice(2)] = next === undefined || next.startsWith("--") ? "true" : (index += 1, next);
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
if (!args.dir) {
  console.error("--dir <models-root> is required (the root the running viewer serves)");
  process.exit(2);
}

const { chromium } = require("playwright");

const failures = [];
const browser = await chromium.launch({
  args: ["--use-angle=metal"]
});

for (const expectation of EXPECTATIONS) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1 });
  await context.addInitScript(([key, version, id]) => {
    window.localStorage.setItem(key, JSON.stringify({ version, themeId: id, custom: null }));
  }, [THEME_STORAGE_KEY, THEME_STORAGE_VERSION, expectation.themeId]);
  const page = await context.newPage();
  const url = `${args.url}${args.dir}?file=${encodeURIComponent(args.file)}`;
  await page.goto(url, { waitUntil: "domcontentloaded" });
  let placement = null;
  try {
    await page.waitForFunction(
      () => Boolean(window.__cadModelPlacement?.position),
      undefined,
      { timeout: 30000 }
    );
    placement = await page.evaluate(() => window.__cadModelPlacement);
  } catch {
    failures.push(`${expectation.themeId}: placement seam never published (model did not load?)`);
  }

  if (placement) {
    const [px, py, pz] = placement.position.map(Number);
    if (Math.abs(px) > 1e-9 || Math.abs(py) > 1e-9 || Math.abs(pz) > 1e-9) {
      failures.push(
        `${expectation.themeId}: model translated to [${placement.position}] — must render at authored coordinates`
      );
    }
    const minZ = Number(placement.boundsMin?.[2]);
    const maxZ = Number(placement.boundsMax?.[2]);
    // The demo plate is an origin-centered Box(60,40,4): authored z=[-2,2].
    // A re-centering regression cannot fake this: it changes world position,
    // not bounds — so pair the bounds check with the position check above.
    if (!(Math.abs(minZ + 2) < 1e-6 && Math.abs(maxZ - 2) < 1e-6)) {
      failures.push(
        `${expectation.themeId}: expected authored plate bounds z=[-2,2], got z=[${minZ},${maxZ}] — wrong fixture?`
      );
    }
    if (expectation.floorEnabled) {
      if (placement.floorFollowsModel !== true) {
        failures.push(`${expectation.themeId}: floor-enabled stage should keep followModel available`);
      }
      // The plate dips to z=-2, so a floor-enabled stage follows it DOWN to the
      // model bottom (downward-only follow, no clipping).
      if (Math.abs(Number(placement.gridFloorZ) + 2) > 1e-6) {
        failures.push(`${expectation.themeId}: stage should follow the model down to z=-2, got ${placement.gridFloorZ}`);
      }
    } else {
      if (placement.floorFollowsModel !== false) {
        failures.push(`${expectation.themeId}: followModel must be inert with the floor disabled`);
      }
      if (placement.gridFloorZ !== null && Math.abs(Number(placement.gridFloorZ)) > 1e-6) {
        failures.push(`${expectation.themeId}: grid must be pinned to world z=0, got ${placement.gridFloorZ}`);
      }
    }
    console.log(
      `${expectation.themeId}: position=[${placement.position}] boundsZ=[${placement.boundsMin?.[2]},${placement.boundsMax?.[2]}] ` +
      `gridFloorZ=${placement.gridFloorZ} follow=${placement.floorFollowsModel}`
    );
  }

  if (args.out) {
    fs.mkdirSync(args.out, { recursive: true });
    await page.waitForTimeout(1200);
    fs.writeFileSync(
      path.join(args.out, `placement-${expectation.themeId}.png`),
      await page.screenshot()
    );
  }
  await context.close();
}

await browser.close();

if (failures.length) {
  console.error("\nPLACEMENT FAILURES:");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log("\nmodel placement conformance: OK");
