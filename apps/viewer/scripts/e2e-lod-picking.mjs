#!/usr/bin/env node
// LOD picking/highlight gate: after viewport LOD swaps a component to a finer
// tessellation, face picking and the selection highlight must still agree with
// the displayed mesh.
//
// The regression this guards (release/0.5.0): the LOD swap replaced the
// display meshData but left the composed selector runtime at level 0, so
// faceIds (selector faceRuns = triangle ranges of ONE tessellation) mislabeled
// the finer mesh's triangles. Symptoms: the selected face highlighted as
// stripes/partially, and picks resolved to occluded faces "through" the
// surface (a mislabeled front triangle reports a back face's row).
//
// Asserts, on the demo plate (a flat box — one +Z top face, o1.1.f3):
//   1. LOD actually swapped (the test is vacuous otherwise);
//   2. every grid click over the plate that reports a +Z-normal face reports
//      THE SAME reference (there is exactly one top planar face);
//   3. no pick reports a -Z normal (the bottom face is occluded from an
//      above-horizon camera: a -Z pick IS a through-pick);
//   4. selecting the top face paints ≥ 98% of the face-covered center region
//      (the broken build measured ~32%: stripes).
//
// Reads the REAL framebuffer via page.screenshot() (see e2e-format-sweep.mjs
// for why canvas sampling is wrong here).
//
// Usage:
//   node viewer/scripts/e2e-lod-picking.mjs --dir <models-root> [--url http://127.0.0.1:3245]
//
// Requires: a viewer serving <models-root>, playwright, and the mounting plate
// built in the examples project (python models/examples/src/mounting_plate.py).

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const { PNG } = require("pngjs");

const PLATE_FILE = "examples/STEP/mounting_plate.step";
const TOP_FACE_MIN_COVERAGE = 0.98;

function parseArgs(argv) {
  const args = { url: "http://127.0.0.1:3245", dir: "" };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--url") args.url = argv[++index] || args.url;
    else if (flag === "--dir") args.dir = argv[++index] || "";
  }
  return args;
}

function fail(message) {
  console.error(`e2e-lod-picking: ${message}`);
  process.exit(1);
}

const args = parseArgs(process.argv.slice(2));
if (!args.dir || !path.isAbsolute(args.dir)) {
  fail("--dir must be the absolute directory the viewer SERVES (its launch cwd)");
}
// --dir is the served root; the plate may sit at models/... under a repo root
// or directly under a models root. ?file= resolves against the SERVED root,
// which is exactly the mistake this probe must not make itself.
const plateRelCandidates = [PLATE_FILE, path.join("models", PLATE_FILE)];
const plateRel = plateRelCandidates.find((candidate) => fs.existsSync(path.join(args.dir, candidate)));
if (!plateRel) {
  fail(`mounting plate not built under ${args.dir} (run its model script in models/examples)`);
}

const pageUrl = `${args.url.replace(/\/$/, "")}${args.dir}?file=${plateRel.split(path.sep).join("/")}`;
const browser = await chromium.launch({ headless: true, args: ["--use-angle=metal"] });
try {
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const lodSwaps = [];
  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  await page.exposeFunction("__recordLod", (detail) => lodSwaps.push(detail));
  await page.addInitScript(() => {
    window.addEventListener("cad:lod-level", (event) => window.__recordLod?.(event.detail));
  });
  await page.goto(pageUrl, { waitUntil: "domcontentloaded" });
  const canvas = page.locator("canvas").first();
  await canvas.waitFor({ state: "visible", timeout: 30000 });
  await page.waitForTimeout(3500);
  const box = await canvas.boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  // Zoom until the top face fills the center: the projected-chord-error
  // trigger upgrades the component, and the swap is what we are testing. Two
  // notches put the plate's top face across the whole sampled region (which
  // the coverage assertion below depends on); a bounded retry covers a busy
  // machine where a wheel burst lands between the scheduler's samples.
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, -400);
  await page.waitForTimeout(600);
  await page.mouse.wheel(0, -400);
  await page.waitForTimeout(2500);
  for (let attempt = 0; attempt < 3 && !lodSwaps.length; attempt += 1) {
    await page.mouse.wheel(0, -100);
    await page.waitForTimeout(1600);
  }
  if (!lodSwaps.length) {
    fail("no cad:lod-level swap fired — the gate is vacuous at this viewport; raise the zoom");
  }
  await page.waitForTimeout(800);

  async function readPick() {
    return await page.evaluate(() => {
      const copy = [...document.querySelectorAll("button")]
        .map((button) => button.textContent || "")
        .find((text) => text.includes("#o")) || "";
      const ref = (copy.match(/#(o[\d.]+\.(?:f|e|v)\d+)/) || [])[1] || "";
      const text = document.body.innerText || "";
      const anchor = text.indexOf("Normal");
      let normal = null;
      if (anchor >= 0) {
        const numbers = text.slice(anchor, anchor + 60).match(/-?\d+(?:\.\d+)?/g);
        if (numbers && numbers.length >= 3) normal = numbers.slice(0, 3).map(Number);
      }
      return { ref, normal };
    });
  }

  const topFaceRefs = new Set();
  let throughPicks = 0;
  for (let gy = 0; gy < 5; gy += 1) {
    for (let gx = 0; gx < 7; gx += 1) {
      const px = box.x + box.width * (0.2 + (0.6 * gx) / 6);
      const py = box.y + box.height * (0.25 + (0.5 * gy) / 4);
      await page.mouse.click(px, py);
      await page.waitForTimeout(120);
      const pick = await readPick();
      if (!pick.ref || !pick.normal) continue;
      if (pick.normal[2] > 0.9) topFaceRefs.add(pick.ref);
      if (pick.normal[2] < -0.9) throughPicks += 1;
    }
  }
  if (topFaceRefs.size !== 1) {
    fail(`the single +Z planar face picked as ${topFaceRefs.size} distinct references: ${[...topFaceRefs].join(", ")}`);
  }
  if (throughPicks > 0) {
    fail(`${throughPicks} grid picks reported a -Z normal — through-picks of the occluded bottom face`);
  }

  // Highlight coverage: select the top face, then measure the highlighted
  // fraction of the center region (which the zoomed face fully covers).
  // Clicking a face that is already selected toggles it OFF (and the grid
  // sweep may have left this face selected), so click-until-selected, twice
  // at most: deselected -> selected, or selected -> deselected -> selected.
  await page.mouse.click(cx, cy - 30);
  await page.waitForTimeout(400);
  let centerPick = await readPick();
  if (!centerPick.ref) {
    await page.mouse.click(cx, cy - 30);
    await page.waitForTimeout(400);
    centerPick = await readPick();
  }
  if (!topFaceRefs.has(centerPick.ref)) {
    fail(`center click picked ${centerPick.ref || "(nothing)"} instead of the top face`);
  }
  const shot = PNG.sync.read(await page.screenshot());
  let highlighted = 0;
  let sampled = 0;
  const x0 = Math.round(shot.width * 0.15);
  const x1 = Math.round(shot.width * 0.55);
  const y0 = Math.round(shot.height * 0.25);
  const y1 = Math.round(shot.height * 0.75);
  for (let y = y0; y < y1; y += 2) {
    for (let x = x0; x < x1; x += 2) {
      const at = (shot.width * y + x) << 2;
      const r = shot.data[at];
      const g = shot.data[at + 1];
      const b = shot.data[at + 2];
      sampled += 1;
      if (b > r + 25 && b > 150 && g > r) highlighted += 1;
    }
  }
  const coverage = highlighted / Math.max(sampled, 1);
  if (coverage < TOP_FACE_MIN_COVERAGE) {
    fail(`selected-face highlight covers ${(coverage * 100).toFixed(1)}% of the face region ` +
      `(< ${TOP_FACE_MIN_COVERAGE * 100}%) — striped/partial highlight`);
  }
  if (pageErrors.length) {
    fail(`page errors during the run:\n${pageErrors.join("\n")}`);
  }
  console.log(
    `e2e-lod-picking: OK — ${lodSwaps.length} LOD swap(s), one top-face reference (${[...topFaceRefs][0]}), ` +
    `0 through-picks, highlight coverage ${(coverage * 100).toFixed(1)}%`
  );
} finally {
  await browser.close();
}
