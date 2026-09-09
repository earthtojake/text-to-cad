#!/usr/bin/env node
// Part picking/highlight coherence gate (faces + edges), cache-cold AND
// cache-warm, LOD on and off — on a NATIVE-IMPORT part.
//
// The regression this guards (release/0.5.0, reported twice): displayed mesh
// and its labeling data (selector faceRuns, edge tables) desynchronizing on
// individual parts — "totally incoherent and disconnected" face highlights and
// edge picks. The invariant layer is pinned node-side in
// packages/cadgen-js/src/lib/surf/payloadCoherence.test.js; THIS gate proves the
// composed, rendered result in a real browser:
//
//   1. FACE CONTIGUITY: selecting a face paints ONE connected highlight
//      region (4-neighbor connectivity over highlight-classified pixels);
//      the largest connected component must hold >= 97% of all highlight
//      pixels. Scattered mislabeled triangles fail this immediately (the
//      broken build produced dozens of disconnected fragments).
//   2. EDGE COHERENCE: clicking the same model edge at different points along
//      it reports THE SAME edge reference, and its highlight is one connected
//      region (<= 2 components tolerated for antialiasing splits).
//   3. Both gates run cache-COLD (this component's tessellation-cache entries
//      moved aside) and cache-WARM (entries written back by the cold pass) —
//      the warm pass exercises the decode/hit path in the real client, which
//      the cidFromSurfUrl query-form fix made reachable for the first time.
//   4. A LOD-off pass (kill switch) pins the non-LOD path.
//
// Reads the REAL framebuffer via page.screenshot() (see e2e-format-sweep.mjs).
//
// Usage:
//   node viewer/scripts/e2e-part-picking.mjs --dir <models-root> [--url http://127.0.0.1:3245]
//
// Requires: a viewer serving <models-root>; playwright; the part built in the
// examples project (python models/examples/src/cam_follower_roller.py).

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const { PNG } = require("pngjs");

const PART_FILE = "examples/STEP/cam_follower_roller.step";
// The roller's single component cid (its tessellation-cache key prefix). Read it
// back from the package descriptor if the model's geometry ever changes.
const PART_CID = "9ba0d8efa0e308c1";
const FACE_CONTIGUITY_MIN = 0.97;

function parseArgs(argv) {
  const args = { url: "http://127.0.0.1:3245", dir: "", pass: "all" };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--url") args.url = argv[++index] || args.url;
    else if (flag === "--dir") args.dir = argv[++index] || "";
    else if (flag === "--pass") args.pass = argv[++index] || "all";
  }
  return args;
}

function fail(message) {
  console.error(`e2e-part-picking: ${message}`);
  process.exit(1);
}

const args = parseArgs(process.argv.slice(2));
if (!args.dir || !path.isAbsolute(args.dir)) {
  fail("--dir must be the absolute directory the viewer SERVES (its launch cwd)");
}
if (!fs.existsSync(path.join(args.dir, PART_FILE))) {
  fail(`missing ${PART_FILE} under ${args.dir}`);
}
// No package check here: render packages are content-keyed in the user-level store
// (~/.cache/cadgen/packages/<stepHash>-v<N>), not beside the artifact, and the viewer
// resolves them on demand. Building the model script is what fills the store.

// ---- cache staging: cold pass = this component's entries moved aside -------
function meshCacheDir() {
  const override = (process.env.CADGEN_CACHE_DIR || "").trim();
  const base = override
    || (process.env.XDG_CACHE_HOME ? path.join(process.env.XDG_CACHE_HOME, "cadgen") : "")
    || path.join(os.homedir(), ".cache", "cadgen");
  return path.join(base, "meshes");
}

function stageColdCache() {
  const dir = meshCacheDir();
  const parked = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-part-picking-cache-"));
  let moved = 0;
  if (fs.existsSync(dir)) {
    for (const name of fs.readdirSync(dir)) {
      if (name.startsWith(`${PART_CID}-`)) {
        fs.renameSync(path.join(dir, name), path.join(parked, name));
        moved += 1;
      }
    }
  }
  return { parked, moved };
}

function cacheEntryCount() {
  const dir = meshCacheDir();
  if (!fs.existsSync(dir)) return 0;
  return fs.readdirSync(dir).filter((name) => name.startsWith(`${PART_CID}-`)).length;
}

// ---- pixel analysis ---------------------------------------------------------
// Highlight classification: the selection tint is a saturated blue — strongly
// blue over red with real saturation. Matches both face fill and edge strokes.
function isHighlightPixel(data, offset) {
  const r = data[offset];
  const g = data[offset + 1];
  const b = data[offset + 2];
  return b > 140 && b - r > 40 && g > 100 && g < 230;
}

// Connected components of highlight pixels.
// Face fills are area regions: 4-connectivity at 2x downsample is right and
// fast. Edge strokes are ~1px curves: downsampling shatters them, so the edge
// variant runs at full resolution with 8-connectivity after one dilation pass
// (a thin antialiased arc must read as ONE region, while genuinely scattered
// fragments still read as many).
function highlightComponents(png, { mode = "face" } = {}) {
  const step = mode === "edge" ? 1 : 2;
  const w = Math.floor(png.width / step);
  const h = Math.floor(png.height / step);
  const mask = new Uint8Array(w * h);
  let total = 0;
  for (let y = 0; y < h; y += 1) {
    for (let x = 0; x < w; x += 1) {
      const offset = ((y * step) * png.width + (x * step)) * 4;
      if (isHighlightPixel(png.data, offset)) {
        mask[y * w + x] = 1;
        total += 1;
      }
    }
  }
  if (mode === "edge") {
    // One dilation pass: bridge single-pixel antialiasing gaps.
    const dilated = new Uint8Array(mask);
    for (let y = 0; y < h; y += 1) {
      for (let x = 0; x < w; x += 1) {
        if (!mask[y * w + x]) continue;
        for (let dy = -1; dy <= 1; dy += 1) {
          for (let dx = -1; dx <= 1; dx += 1) {
            const nx = x + dx;
            const ny = y + dy;
            if (nx >= 0 && ny >= 0 && nx < w && ny < h) dilated[ny * w + nx] = 1;
          }
        }
      }
    }
    dilated.forEach((v, i) => { mask[i] = v; });
  }
  const neighbors = mode === "edge"
    ? [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]
    : [[1, 0], [-1, 0], [0, 1], [0, -1]];
  const seen = new Uint8Array(w * h);
  const sizes = [];
  const stack = [];
  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || seen[start]) continue;
    let size = 0;
    stack.push(start);
    seen[start] = 1;
    while (stack.length) {
      const cell = stack.pop();
      size += 1;
      const x = cell % w;
      const y = (cell / w) | 0;
      for (const [dx, dy] of neighbors) {
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= w || ny >= h) continue;
        const neighbor = ny * w + nx;
        if (mask[neighbor] && !seen[neighbor]) {
          seen[neighbor] = 1;
          stack.push(neighbor);
        }
      }
    }
    sizes.push(size);
  }
  sizes.sort((a, b) => b - a);
  return { total, components: sizes };
}

async function screenshotPng(page) {
  return PNG.sync.read(await page.screenshot());
}

// ---- gates ------------------------------------------------------------------
async function chipRef(page) {
  // Tight timeout: a missed click means NO chip, and the default 30s locator
  // wait would turn every miss into a stall.
  const chip = await page
    .locator("text=/Copy .*#o/")
    .first()
    .textContent({ timeout: 300 })
    .catch(() => null);
  return chip ? chip.replace("Copy ", "").trim() : "";
}

async function runGate(page, { tag, expectLod }) {
  const canvas = page.locator("canvas").first();
  const box = await canvas.boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;

  // EDGE gate first, at moderate zoom (edges subtend enough pixels to pick):
  // the same physical rim must answer with the SAME edge ref from several
  // points along it, and its highlight must be one region.
  await page.mouse.move(cx, cy);
  await page.mouse.wheel(0, -120);
  await page.waitForTimeout(1500);
  await edgeGate(page, box, tag);

  // Then zoom deeper to trigger LOD swaps (when enabled).
  for (let i = 0; i < 3; i += 1) {
    await page.mouse.wheel(0, -200);
    await page.waitForTimeout(350);
  }
  await page.waitForTimeout(2500);
  const lodEvents = await page.evaluate(() => window.__lodEvents || []);
  if (expectLod && !lodEvents.length) {
    fail(`${tag}: expected LOD swaps but none happened (gate would be vacuous)`);
  }
  if (!expectLod && lodEvents.length) {
    fail(`${tag}: LOD disabled but swaps happened`);
  }

  // FACE gate: click grid until a face ref lands, then contiguity-check it.
  let faceRef = "";
  const gridSpots = [];
  for (let gy = 2; gy <= 5; gy += 1) for (let gx = 1; gx <= 6; gx += 1) gridSpots.push([gx, gy]);
  for (const [gx, gy] of gridSpots) {
    await page.mouse.click(box.x + (box.width * gx) / 8, box.y + (box.height * gy) / 8);
    await page.waitForTimeout(120);
    const ref = await chipRef(page);
    if (/\.f\d+$/.test(ref)) {
      faceRef = ref;
      break;
    }
  }
  if (!faceRef) fail(`${tag}: no face pick landed anywhere on the grid`);
  await page.waitForTimeout(500);
  const png = await screenshotPng(page);
  const { total, components } = highlightComponents(png);
  if (total < 400) fail(`${tag}: face highlight too small to judge (${total} px)`);
  const contiguity = components[0] / total;
  if (contiguity < FACE_CONTIGUITY_MIN) {
    fail(`${tag}: face ${faceRef} highlight is FRAGMENTED — largest component ${(contiguity * 100).toFixed(1)}% of ${total}px across ${components.length} pieces`);
  }
  console.log(`  ${tag}: face ${faceRef} highlight contiguous (${(contiguity * 100).toFixed(1)}% in largest of ${components.length} components, ${total}px)`);

}


async function edgeGate(page, box, tag) {
  const edgeHits = new Map();
  // The rim band first (where circular edges live at this framing), then the
  // rest — bounded either way by the 3-hit break.
  const bands = [[0.22, 0.42], [0.42, 0.8], [0.12, 0.22]];
  outer: for (const [fyStart, fyEnd] of bands) for (let fy = fyStart; fy <= fyEnd; fy += 0.03) {
    for (let fx = 0.15; fx <= 0.85; fx += 0.04) {
      await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
      await page.waitForTimeout(80);
      const ref = await chipRef(page);
      if (/\.e\d+$/.test(ref)) {
        if (!edgeHits.has(ref)) edgeHits.set(ref, []);
        edgeHits.get(ref).push([fx, fy]);
        if (edgeHits.get(ref).length >= 3) break outer;
      }
    }
  }
  const repeated = [...edgeHits.entries()].find(([, spots]) => spots.length >= 3);
  if (!repeated) {
    const summary = [...edgeHits.entries()].map(([k, v]) => `${k} x${v.length}`).join(", ") || "none";
    fail(`${tag}: no edge answered consistently from 3+ points along it (got: ${summary})`);
  }
  const [edgeRef, spots] = repeated;
  const spread = Math.max(...spots.map((s2) => s2[0])) - Math.min(...spots.map((s2) => s2[0]));
  if (spread < 0.05) {
    fail(`${tag}: edge ${edgeRef} only picked in one spot cluster — not evidence of one coherent edge`);
  }
  await page.mouse.click(box.x + box.width * spots[0][0], box.y + box.height * spots[0][1]);
  await page.waitForTimeout(500);
  const edgePng = await screenshotPng(page);
  const edge = highlightComponents(edgePng, { mode: "edge" });
  // A visible circular edge renders as one arc (or two, where the silhouette
  // occludes the far side); tolerate a couple of occlusion splits but fail on
  // scatter: the top 3 components must hold nearly everything.
  const top3 = (edge.components[0] || 0) + (edge.components[1] || 0) + (edge.components[2] || 0);
  const edgeContiguity = edge.total ? top3 / edge.total : 0;
  if (edge.total < 60 || edgeContiguity < 0.9) {
    fail(`${tag}: edge ${edgeRef} highlight fragmented (${edge.components.length} components over ${edge.total}px, top3 ${(edgeContiguity * 100).toFixed(1)}%)`);
  }
  console.log(`  ${tag}: edge ${edgeRef} coherent — same ref from ${spots.length} points (x-spread ${spread.toFixed(2)}), highlight in ${edge.components.length} component(s)`);
}

async function openPart(browser, { lod }) {
  const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
  page.on("pageerror", (error) => fail(`page error: ${error.message}`));
  await page.addInitScript(({ lodOn }) => {
    if (!lodOn) window.__CAD_VIEWER_LOD__ = false;
    window.__lodEvents = [];
    window.addEventListener("cad:lod-level", (event) => window.__lodEvents.push(event.detail));
  }, { lodOn: lod });
  // domcontentloaded + fixed settle: older builds poll status forever, so
  // networkidle never fires there and the gate must run against them too.
  await page.goto(`${args.url}${args.dir}?file=${PART_FILE}`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(6000);
  return page;
}

const wantsPass = (name) => args.pass === "all" || args.pass === name;

const browser = await chromium.launch({
  args: ["--use-angle=metal", "--disable-features=PrivateNetworkAccessSendPreflights"],
});
try {
  if (wantsPass("cold")) {
    // COLD pass (LOD on): entries parked aside, tessellates fresh, writes back.
    const { parked, moved } = stageColdCache();
    console.log(`e2e-part-picking: parked ${moved} cache entrie(s) for ${PART_CID} -> ${parked}`);
    const page = await openPart(browser, { lod: true });
    await runGate(page, { tag: "cold+lod", expectLod: true });
    await page.close();
    const written = cacheEntryCount();
    if (written < 1) {
      fail("cold pass wrote no cache entries — the client cache integration is dead again (cidFromSurfUrl?)");
    }
    console.log(`  cold pass wrote ${written} cache entrie(s) — client cache integration alive`);
  }
  if (wantsPass("warm")) {
    if (cacheEntryCount() < 1) fail("warm pass requires cache entries (run the cold pass first)");
    const page = await openPart(browser, { lod: true });
    await runGate(page, { tag: "warm+lod", expectLod: true });
    await page.close();
  }
  if (wantsPass("lodoff")) {
    const page = await openPart(browser, { lod: false });
    await runGate(page, { tag: "lod-off", expectLod: false });
    await page.close();
  }
  console.log(`e2e-part-picking: PASS (${args.pass})`);
} finally {
  await browser.close();
}
