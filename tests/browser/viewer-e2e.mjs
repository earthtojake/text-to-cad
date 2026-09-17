#!/usr/bin/env node
// Real-browser coverage for the bundled Viewer's cross-format, placement,
// appearance, LOD, and selector coherence contracts. Fixture and process
// lifecycle belong to scripts/test/test-viewer-browser.sh.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const { chromium } = createRequire(path.join(REPO, "packages/cadgen-js/package.json"))("playwright");
const { PNG } = createRequire(path.join(REPO, "apps/viewer/package.json"))("pngjs");

function parseArgs(argv) {
  const args = { url: "", dir: "", out: "", only: "", ci: false };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === "--url") args.url = argv[++i] || "";
    else if (flag === "--dir") args.dir = argv[++i] || "";
    else if (flag === "--out") args.out = argv[++i] || "";
    // One gate at a time while working on it: --only kinematics.
    else if (flag === "--only") args.only = argv[++i] || "";
    // The CI-sized subset. See CI_GATES.
    else if (flag === "--ci") args.ci = true;
    else throw new Error(`unknown argument: ${flag}`);
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const root = path.resolve(args.dir || ".");
const fixtures = [
  // `measure` mirrors renderCapabilities: a view that cannot measure has NO Measure
  // button (hidden, not disabled).
  { format: "stl", file: "smoke.stl", parts: false, measure: true },
  { format: "3mf", file: "smoke.3mf", parts: false, measure: true },
  { format: "glb", file: "smoke.glb", parts: false, measure: true },
  { format: "step", file: "assembly.step", parts: true, measure: true },
  { format: "dxf", file: "smoke.dxf", parts: false, measure: false },
  { format: "urdf", file: "smoke.urdf", parts: false, measure: false },
  { format: "srdf", file: "smoke.srdf", parts: false, measure: false },
];
const expectedBounds = { min: [39, -3, -5], max: [45, 3, 9] };
const viewport = { width: 1400, height: 900 };
const viewerOrigin = args.url ? new URL(args.url).origin : "";
const latestReleaseApiUrl = "https://api.github.com/repos/earthtojake/text-to-cad/releases/latest";
const currentVersion = fs.readFileSync(path.join(REPO, "VERSION"), "utf8").trim();
const failures = [];
const results = [];

function fail(message) {
  throw new Error(message);
}

if (!args.url) fail("--url is required; use the self-contained scripts/test runner");
if (!args.dir || !path.isAbsolute(args.dir)) fail("--dir must name the absolute served test project");
for (const fixture of fixtures) {
  if (!fs.existsSync(path.join(root, fixture.file))) fail(`missing test input ${fixture.file}`);
}

const angle = process.platform === "darwin" ? "metal" : "swiftshader";
const browserFlags = [`--use-angle=${angle}`, "--ignore-gpu-blocklist"];
if (angle === "swiftshader") browserFlags.push("--enable-unsafe-swiftshader");
console.log(`viewer browser e2e: Chromium ANGLE=${angle}`);
const browser = await chromium.launch({
  headless: true,
  args: browserFlags,
});

async function newPage({ lod = true } = {}) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const errors = [];
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = request.url();
    if (url === latestReleaseApiUrl && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tag_name: `v${currentVersion}`,
          html_url: `https://github.com/earthtojake/text-to-cad/releases/tag/v${currentVersion}`,
          body: "",
        }),
      });
      return;
    }
    const parsed = new URL(url);
    if (["http:", "https:"].includes(parsed.protocol) && parsed.origin !== viewerOrigin) {
      errors.push(`unexpected external request: ${request.method()} ${url} (${request.resourceType()})`);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(`page: ${error.message || error}`));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const location = message.location();
    const source = location.url
      ? ` at ${location.url}:${Number(location.lineNumber) + 1}:${Number(location.columnNumber) + 1}`
      : "";
    errors.push(`console: ${message.text()}${source}`);
  });
  await page.addInitScript(({ lodOn }) => {
    if (!lodOn) window.__CAD_VIEWER_LOD__ = false;
    window.__viewerTestLodEvents = [];
    window.addEventListener("cad:lod-level", (event) => window.__viewerTestLodEvents.push(event.detail));
  }, { lodOn: lod });
  return {
    context,
    page,
    errors,
  };
}

async function openFile(page, file) {
  await page.goto(`${args.url.replace(/\/$/, "")}/?file=${encodeURIComponent(file)}`, {
    waitUntil: "domcontentloaded",
    timeout: 60_000,
  });
  await page.getByRole("button", { name: /^Viewing mode:/ }).waitFor({ timeout: 60_000 });
  const canvas = page.locator("canvas").first();
  await canvas.waitFor({ state: "visible", timeout: 60_000 });
  await page.waitForFunction(() => !document.querySelector(".cad-loading-overlay"), null, { timeout: 120_000 });
  // Then settle on the seam that says the model reached the RENDERER, not on a
  // second of wall clock. Every fixture format publishes it — the format gate
  // asserts its bounds for all seven — so this is a state wait on a slow runner
  // and a shortcut on a fast one. The short pause after it is for the frame to
  // be painted, which has no seam of its own.
  await page.waitForFunction(() => {
    const placement = window.__cadModelPlacement;
    const min = placement?.boundsMin;
    const max = placement?.boundsMax;
    return Array.isArray(min) && Array.isArray(max)
      && min.some((value, axis) => Number(max[axis]) - Number(value) > 0);
  }, null, { timeout: 120_000 });
  await page.waitForTimeout(250);
  return canvas;
}

function isHighlight(data, offset) {
  const r = data[offset];
  const g = data[offset + 1];
  const b = data[offset + 2];
  return b > 140 && b - r > 40 && g > 100 && g < 230;
}

function highlightMask(png, step, sceneWidth) {
  const width = Math.floor(png.width / step);
  const height = Math.floor(png.height / step);
  const columns = Math.min(width, Math.ceil(sceneWidth / step));
  const mask = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) for (let x = 0; x < columns; x += 1) {
    if (isHighlight(png.data, ((y * step) * png.width + x * step) * 4)) mask[y * width + x] = 1;
  }
  return { mask, width, height };
}

// What the selection ADDED to the scene, not every blue pixel on the page. The
// docked reference panel is blue-on-white and only appears once something is
// selected, and the orientation gizmo is permanently blue, so a whole-page mask
// scored both as dozens of extra highlight "pieces" (67 over 7834px here) no
// matter how coherent the highlight itself was. Clipping at the panel and
// subtracting the unselected frame leaves exactly the pixels the pick lit up.
function highlightComponents(selected, baseline, sceneWidth, mode = "face") {
  const step = mode === "edge" ? 1 : 2;
  const lit = highlightMask(selected, step, sceneWidth);
  const before = highlightMask(baseline, step, sceneWidth);
  const { width, height } = lit;
  let mask = new Uint8Array(lit.mask.length);
  for (let i = 0; i < mask.length; i += 1) mask[i] = lit.mask[i] && !before.mask[i] ? 1 : 0;
  if (mode === "edge") {
    const dilated = new Uint8Array(mask);
    for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
      if (!mask[y * width + x]) continue;
      for (let dy = -1; dy <= 1; dy += 1) for (let dx = -1; dx <= 1; dx += 1) {
        const nx = x + dx;
        const ny = y + dy;
        if (nx >= 0 && ny >= 0 && nx < width && ny < height) dilated[ny * width + nx] = 1;
      }
    }
    mask = dilated;
  }
  const directions = mode === "edge"
    ? [[1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [1, -1], [-1, 1], [-1, -1]]
    : [[1, 0], [-1, 0], [0, 1], [0, -1]];
  const seen = new Uint8Array(mask.length);
  const sizes = [];
  for (let start = 0; start < mask.length; start += 1) {
    if (!mask[start] || seen[start]) continue;
    const stack = [start];
    seen[start] = 1;
    let size = 0;
    while (stack.length) {
      const cell = stack.pop();
      size += 1;
      const x = cell % width;
      const y = (cell / width) | 0;
      for (const [dx, dy] of directions) {
        const nx = x + dx;
        const ny = y + dy;
        const next = ny * width + nx;
        if (nx >= 0 && ny >= 0 && nx < width && ny < height && mask[next] && !seen[next]) {
          seen[next] = 1;
          stack.push(next);
        }
      }
    }
    sizes.push(size);
  }
  sizes.sort((a, b) => b - a);
  return { total: mask.reduce((sum, value) => sum + value, 0), sizes };
}

async function chipRef(page) {
  const chip = page.locator("text=/Copy .*#o/").first();
  const text = await chip.count() ? await chip.textContent({ timeout: 100 }).catch(() => "") : "";
  return text ? text.replace("Copy ", "").trim() : "";
}

// Desktop activation is deliberately delayed 220ms so a second click can still
// become a double click, and the chip only changes once that timer commits.
// Reading it a fixed 240ms after the click left ~20ms for the commit plus the
// React render and lost that race on a fast Linux box. (No pair of these clicks
// can become a real dblclick: Playwright dispatches each one with clickCount 1,
// so the page never sees detail=2.) A miss must be waited out, a state change
// must not be.
const ACTIVATION_SETTLE_MS = 700;

// MEASURED, do not shorten: polling for "a chip exists" and taking the first one
// does NOT work. A pick publishes a reference as soon as the pointer goes up and
// the activation timer REPLACES it 220 ms later, so an early read returns the
// pre-activation answer — the edge search saw solid references at every one of its
// 113 probe points and found no edge at all. Sleep past the commit, then read.
async function clickForChip(page, x, y) {
  await page.mouse.click(x, y);
  await page.waitForTimeout(ACTIVATION_SETTLE_MS);
  return chipRef(page);
}

async function clickUntilChip(page, x, y, accept, timeout = 5_000) {
  await page.mouse.click(x, y);
  const deadline = Date.now() + timeout;
  let ref = await chipRef(page);
  while (!accept(ref) && Date.now() < deadline) {
    await page.waitForTimeout(100);
    ref = await chipRef(page);
  }
  return ref;
}

// Emptying the selection is bookkeeping between probes, so it uses the one
// gesture whose outcome does not depend on what the raycast hits: a click on
// bare background clears, whatever was selected. Clicking the selected
// geometry again does not qualify -- see toggleOff.
const BACKGROUND = [0.03, 0.5];

async function clearSelection(page, box, tag) {
  if (!(await chipRef(page))) return;
  const left = await clickUntilChip(
    page, box.x + box.width * BACKGROUND[0], box.y + box.height * BACKGROUND[1], (value) => !value,
  );
  if (left) fail(`${tag}: a background click left ${left} selected`);
}

// The toggle contract, in full: a reference's own second click empties the
// selection, and a third click at the same pixel brings the SAME reference
// back. Landing on the neighbouring face instead is not a pass -- that is
// either a silhouette still moving (settle before asserting, never sleep) or
// the picking bug this gate exists to catch.
async function toggleOff(page, x, y, ref, tag) {
  const stuck = await clickUntilChip(page, x, y, (value) => !value);
  if (stuck) fail(`${tag}: clicking ${ref} twice left ${stuck} selected`);
}

// The docked tree/reference panel overlays the canvas on the right; its tabs
// mark its left edge. Highlight measurements stop there.
async function sceneWidth(page) {
  const left = await page.evaluate((half) => {
    const lefts = [...document.querySelectorAll('[role="tab"], [role="tablist"]')]
      .map((node) => node.getBoundingClientRect())
      .filter((rect) => rect.width > 0 && rect.height > 0 && rect.left > half)
      .map((rect) => rect.left);
    return lefts.length ? Math.min(...lefts) : 0;
  }, viewport.width / 2);
  return left > 0 ? Math.floor(left) : viewport.width;
}

// Two clicks at one pixel only mean anything when they see the same geometry,
// and the only thing that moves the silhouette under a stationary cursor is a
// LOD swap. Wait the scheduler out on the same seam the quality gate reads --
// never a sleep. With LOD off nothing swaps, so opening the file is the whole
// settle.
async function settleLod(page, lod) {
  if (!lod) return;
  await page.waitForFunction(() => {
    const snapshot = window.__cadViewportLod?.();
    return !!snapshot && snapshot.componentCount > 0 && snapshot.qualitySettled === true
      && !snapshot.busy && !snapshot.pendingEvaluation && !snapshot.collectionPending;
  }, null, { timeout: 60_000 });
}

// Park the pointer over the panel so a hover highlight cannot join the mask,
// and settle the frame before reading it.
async function restingShot(page) {
  await page.mouse.move(viewport.width - 4, viewport.height - 4);
  await page.waitForTimeout(400);
  return PNG.sync.read(await page.screenshot());
}

// Where the model actually IS, read off the frame rather than guessed as a
// fraction of the canvas. The fitted model is not centred on the canvas -- the
// docked panel takes the right third -- and after a zoom it is wherever the
// anchor left it, so a hard-coded fraction is a pixel lottery. Take the median
// foreground pixel: for one convex-ish silhouette that point is inside it, well
// away from the edges the 10 px edge-pick window guards.
function drawnModelPoint(png, sceneWidth) {
  const buckets = new Map();
  const columns = Math.min(png.width, Math.max(1, Math.floor(sceneWidth)));
  for (let y = 0; y < png.height; y += 2) for (let x = 0; x < columns; x += 2) {
    const offset = (y * png.width + x) * 4;
    const key = [png.data[offset], png.data[offset + 1], png.data[offset + 2]]
      .map((value) => Math.round(value / 8) * 8).join(",");
    buckets.set(key, (buckets.get(key) || 0) + 1);
  }
  const background = String([...buckets].sort((a, b) => b[1] - a[1])[0]?.[0] || "0,0,0")
    .split(",").map(Number);
  const xs = [];
  const ys = [];
  for (let y = 0; y < png.height; y += 2) for (let x = 0; x < columns; x += 2) {
    const offset = (y * png.width + x) * 4;
    const delta = Math.abs(png.data[offset] - background[0])
      + Math.abs(png.data[offset + 1] - background[1])
      + Math.abs(png.data[offset + 2] - background[2]);
    if (delta > 32) { xs.push(x); ys.push(y); }
  }
  if (xs.length < 200) return null;
  const median = (values) => values.sort((a, b) => a - b)[Math.floor(values.length / 2)];
  return [median(xs), median(ys)];
}

// Pick a face and prove the pick reached the renderer: the chip names a face
// reference, the framebuffer changes in ONE connected region (a fragmented
// highlight means the pick and the drawn geometry disagree), and the reference
// toggles off and back on at the same pixel. This is the whole "pick a face"
// user flow, and it is what the CI subset runs.
async function facePickPhase(page, box, scene, tag, { toggle = false, at = null } = {}) {
  const baseline = await restingShot(page);
  // `at` is the pixel the caller zoomed toward, which the wheel keeps under the
  // cursor, so the model is still there. Without one, walk out from the canvas
  // centre.
  const probes = at
    ? [[0, 0], [-24, 0], [24, 0], [0, -24], [0, 24]].map(([dx, dy]) => [at[0] + dx, at[1] + dy])
    : [[0.5, 0.5], [0.45, 0.5], [0.55, 0.5], [0.5, 0.4], [0.5, 0.6]]
      .map(([fx, fy]) => [box.x + box.width * fx, box.y + box.height * fy]);
  let faceRef = "";
  let spot = null;
  const seen = [];
  for (const point of probes) {
    const ref = await clickForChip(page, point[0], point[1]);
    seen.push(`(${Math.round(point[0])},${Math.round(point[1])})->${ref || "none"}`);
    if (/\.f\d+$/.test(ref)) { faceRef = ref; spot = point; }
    if (faceRef) break;
  }
  if (!faceRef) {
    if (args.out) {
      fs.mkdirSync(args.out, { recursive: true });
      fs.writeFileSync(path.join(args.out, `${tag}-face-miss.png`), await page.screenshot());
    }
    fail(`${tag}: no face pick landed on the rendered cylinder — ${seen.join(", ")}`);
  }
  const face = highlightComponents(await restingShot(page), baseline, scene);
  const ratio = face.total ? (face.sizes[0] || 0) / face.total : 0;
  if (face.total < 300 || ratio < 0.97) {
    if (args.out) {
      fs.mkdirSync(args.out, { recursive: true });
      fs.writeFileSync(path.join(args.out, `${tag}-face-highlight.png`), await page.screenshot());
    }
    fail(`${tag}: face ${faceRef} highlight fragmented (${(ratio * 100).toFixed(1)}%, ${face.total}px)`);
  }
  // The toggle contract: the reference's own second click empties the selection and
  // a third at the same pixel brings the SAME reference back. The full gate asserts
  // this on the edge it found, where the pixel is far harder to hit twice; the CI
  // subset, which never runs the edge phase, asserts it here.
  if (toggle) {
    await toggleOff(page, spot[0], spot[1], faceRef, tag);
    const retoggled = await clickUntilChip(page, spot[0], spot[1], (value) => !!value);
    if (retoggled !== faceRef) {
      fail(`${tag}: re-clicking the toggled ${faceRef} produced ${retoggled || "no chip"}`);
    }
  }
  return { faceRef, ratio };
}

async function pickingGate(tag, lod, { depth = "full" } = {}) {
  const { context, page, errors } = await newPage({ lod });
  try {
    const canvas = await openFile(page, "smoke.step");
    const box = await canvas.boundingBox();
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.move(cx, cy);
    await page.mouse.wheel(0, -120);
    await page.waitForTimeout(1200);
    await settleLod(page, lod);

    const edgeHits = new Map();
    const probePoints = [];
    // The CI subset stops here: opening a STEP package, settling LOD, picking a face
    // and toggling it is the user-visible flow ("click the model, get a reference
    // back"). The edge phase below costs ~30 probe clicks at the activation window
    // each, which is what keeps the full gate out of a CI budget.
    if (depth === "smoke") {
      const scene = await sceneWidth(page);
      // Zoom the way the full gate does before ITS face probes, anchored on the
      // drawn model so the zoom keeps it in frame. At the fitted scale the front
      // face is crossed by its own topology edge overlay, which splits the
      // highlight into pieces that have nothing to do with the pick; zoomed in,
      // the face fills the view and a fragmented highlight means what it says.
      const fitted = drawnModelPoint(await restingShot(page), scene);
      if (!fitted) fail(`${tag}: no drawn model to aim at`);
      await page.mouse.move(fitted[0], fitted[1]);
      for (let i = 0; i < 3; i += 1) {
        await page.mouse.wheel(0, -220);
        await page.waitForTimeout(400);
      }
      await settleLod(page, lod);
      const { faceRef, ratio } = await facePickPhase(page, box, scene, tag, { toggle: true, at: fitted });
      if (errors.length) fail(`${tag}: ${errors.join(" | ")}`);
      console.log(`  ${tag}: face ${faceRef} picked and ${(ratio * 100).toFixed(1)}% contiguous, `
        + "and it toggles off and back on at the same pixel");
      return;
    }
    // The cylinder's visible generator is vertical near the canvas center.
    // Probe it densely before the bounded general grid so edge hit tolerance
    // does not turn this into a hundreds-of-timeouts search.
    for (let fx = 0.25; fx <= 0.48; fx += 0.01) {
      for (const fy of [0.11, 0.12, 0.13]) probePoints.push([fx, fy]);
    }
    for (const fx of [0.554, 0.557, 0.560, 0.563, 0.566]) {
      for (const fy of [0.20, 0.40, 0.60, 0.72]) probePoints.push([fx, fy]);
    }
    for (const fx of [0.24, 0.30, 0.36, 0.42, 0.48, 0.54, 0.60, 0.63]) {
      for (const fy of [0.12, 0.22, 0.34]) probePoints.push([fx, fy]);
    }
    let probes = 0;
    outer: for (const [fx, fy] of probePoints) {
        probes += 1;
        const ref = await clickForChip(page, box.x + box.width * fx, box.y + box.height * fy);
        if (!/\.e\d+$/.test(ref)) continue;
        if (!edgeHits.has(ref)) edgeHits.set(ref, []);
        edgeHits.get(ref).push([fx, fy]);
        const hits = edgeHits.get(ref);
        const separated = hits.some(([x1, y1]) => hits.some(([x2, y2]) => Math.hypot(x2 - x1, y2 - y1) >= 0.08));
        // Empty the selection before the next probe. Otherwise an empty click
        // can leave the previous chip visible and manufacture repeats.
        await clearSelection(page, box, tag);
        if (hits.length >= 2 && separated) break outer;
    }
    const repeated = [...edgeHits.entries()].find(([, spots]) => (
      spots.length >= 2
      && spots.some(([x1, y1]) => spots.some(([x2, y2]) => Math.hypot(x2 - x1, y2 - y1) >= 0.08))
    ));
    if (!repeated) {
      if (args.out) {
        fs.mkdirSync(args.out, { recursive: true });
        fs.writeFileSync(path.join(args.out, `${tag}-edge-scan.png`), await page.screenshot());
      }
      const summary = [...edgeHits]
        .map(([ref, hits]) => `${ref} ${hits.map(([x, y]) => `(${x.toFixed(3)},${y.toFixed(2)})`).join(" ")}`)
        .join(", ") || "no edge refs";
      fail(`${tag}: no edge returned one stable reference across two separated points after ${probes} probes (${summary})`);
    }
    const [edgeRef, spots] = repeated;
    const scene = await sceneWidth(page);
    // Everything below is one pixel clicked three times, so it runs against a
    // settled scheduler: the point is sampled from the geometry all three
    // clicks will see.
    await settleLod(page, lod);
    const spotX = box.x + box.width * spots[0][0];
    const spotY = box.y + box.height * spots[0][1];
    const edgeBaseline = await restingShot(page);
    const reselected = await clickUntilChip(page, spotX, spotY, (value) => !!value);
    if (reselected !== edgeRef) fail(`${tag}: reselecting ${edgeRef} produced ${reselected || "no chip"}`);
    // A pick can resolve a pinned surface; let that land before measuring.
    await settleLod(page, lod);
    const edge = highlightComponents(await restingShot(page), edgeBaseline, scene, "edge");
    const top3 = (edge.sizes[0] || 0) + (edge.sizes[1] || 0) + (edge.sizes[2] || 0);
    if (edge.total < 60 || top3 / edge.total < 0.9) {
      if (args.out) {
        fs.mkdirSync(args.out, { recursive: true });
        fs.writeFileSync(path.join(args.out, `${tag}-edge-highlight.png`), await page.screenshot());
      }
      fail(`${tag}: edge ${edgeRef} highlight fragmented (${edge.sizes.length} pieces over ${edge.total}px)`);
    }
    // Return to an empty selection before face probes, so a miss cannot inherit
    // the edge chip whose framebuffer was just checked. The scene is quiet here,
    // so this is also where the toggle contract is asserted: the second click
    // empties the selection, and the third returns the same reference.
    await toggleOff(page, spotX, spotY, edgeRef, tag);
    await settleLod(page, lod);
    const retoggled = await clickUntilChip(page, spotX, spotY, (value) => !!value);
    if (retoggled !== edgeRef) {
      fail(`${tag}: re-clicking the toggled ${edgeRef} produced ${retoggled || "no chip"}`);
    }
    await clearSelection(page, box, tag);

    // The wheel zooms toward the cursor, and at 7x the model leaves the frame
    // unless the anchor is ON it. Park the pointer on the edge point, which is
    // the silhouette: the face probes then still land on the cylinder. This was
    // previously left to wherever the last click of the edge phase happened to
    // put the pointer.
    await page.mouse.move(spotX, spotY);
    for (let i = 0; i < 3; i += 1) {
      await page.mouse.wheel(0, -220);
      await page.waitForTimeout(400);
    }
    await page.waitForTimeout(2000);
    const lodEvents = await page.evaluate(() => window.__viewerTestLodEvents || []);
    if (lod && !lodEvents.length) fail(`${tag}: no LOD swap fired`);
    if (!lod && lodEvents.length) fail(`${tag}: LOD-off page emitted swaps`);

    const { faceRef, ratio } = await facePickPhase(page, box, scene, tag);
    if (errors.length) fail(`${tag}: ${errors.join(" | ")}`);
    console.log(`  ${tag}: ${lodEvents.length} LOD swap(s), face ${faceRef} ${(ratio * 100).toFixed(1)}% contiguous, `
      + `edge ${edgeRef} coherent (found by ${probes} probes)`);
  } finally {
    await context.close();
  }
}

function coverage(png) {
  const buckets = new Map();
  for (let offset = 0; offset < png.data.length; offset += 44) {
    const key = [png.data[offset], png.data[offset + 1], png.data[offset + 2]]
      .map((value) => Math.round(value / 8) * 8).join(",");
    buckets.set(key, (buckets.get(key) || 0) + 1);
  }
  const background = String([...buckets].sort((a, b) => b[1] - a[1])[0]?.[0] || "0,0,0").split(",").map(Number);
  let covered = 0;
  let sampled = 0;
  for (let offset = 0; offset < png.data.length; offset += 44) {
    sampled += 1;
    const delta = Math.abs(png.data[offset] - background[0])
      + Math.abs(png.data[offset + 1] - background[1])
      + Math.abs(png.data[offset + 2] - background[2]);
    if (delta > 32) covered += 1;
  }
  return covered / Math.max(sampled, 1);
}

async function canvasMenuItems(page, canvas) {
  const box = await canvas.boundingBox();
  const point = { x: box.x + box.width * 0.12, y: box.y + box.height * 0.86 };
  await page.mouse.click(point.x, point.y, { button: "right" });
  await page.waitForTimeout(300);
  const menu = page.locator('[role="menu"]').first();
  const items = await menu.count() ? (await menu.locator('[role="menuitem"]').allTextContents()).map((x) => x.trim()) : [];
  await page.keyboard.press("Escape");
  return items;
}

async function formatGate() {
  // Fullscreen is the floating toolbar's rightmost button. Measure is absent, not
  // disabled, on views that cannot measure, so it is asserted per capability below.
  const tools = ["Select", "Pan", "Draw", "Copy screenshot", "Fullscreen"];
  const camera = ["Reset Zoom", "Zoom To Fit"];
  const tree = ["Show all", "Expand all", "Collapse all"];
  const presentTree = ["Expand all", "Collapse all"];
  // One fixture per LOAD PATH under --ci: an exact-surface STEP package, a mesh,
  // a 2D drawing, a robot description. The three left out are parity cases over a
  // path already covered here — 3mf and glb reach the same mesh loader as stl, and
  // srdf is urdf plus planning semantics — so the full run keeps them and the CI
  // run spends the ~8 s elsewhere.
  const CI_FORMATS = new Set(["step", "stl", "dxf", "urdf"]);
  const selectedFixtures = args.ci ? fixtures.filter(({ format }) => CI_FORMATS.has(format)) : fixtures;
  for (const fixture of selectedFixtures) {
    const { context, page, errors } = await newPage();
    try {
      const canvas = await openFile(page, fixture.file);
      const shot = PNG.sync.read(await canvas.screenshot());
      const drawn = coverage(shot);
      const placement = await page.evaluate(() => window.__cadModelPlacement || null);
      const spans = placement?.boundsMin?.map((value, axis) => Number(placement.boundsMax?.[axis]) - Number(value)) || [];
      if (!spans.some((value) => Number.isFinite(value) && value > 0)) {
        failures.push(`${fixture.format}: no non-empty model bounds reached the renderer`);
      }
      if (drawn < 0.03) failures.push(`${fixture.format}: no foreground model region (${drawn.toFixed(4)})`);
      for (const label of tools) {
        const button = page.locator(`button[aria-label="${label}"]`).first();
        if (!(await button.count()) || !(await button.isEnabled())) failures.push(`${fixture.format}: missing or disabled ${label}`);
      }
      const measure = page.locator('button[aria-label="Measure"]');
      const measureCount = await measure.count();
      if (fixture.measure && (!measureCount || !(await measure.first().isEnabled()))) {
        failures.push(`${fixture.format}: missing or disabled Measure`);
      } else if (!fixture.measure && measureCount) {
        failures.push(`${fixture.format}: Measure is offered on a view that cannot measure (must be hidden, not disabled)`);
      }
      const menu = await canvasMenuItems(page, canvas);
      for (const item of camera) if (!menu.includes(item)) failures.push(`${fixture.format}: menu missing ${item}`);
      if (fixture.parts) {
        for (const item of presentTree) if (!menu.includes(item)) failures.push(`${fixture.format}: parts menu missing ${item}`);
      } else {
        for (const item of tree) if (menu.includes(item)) failures.push(`${fixture.format}: tree action ${item} leaked without parts`);
      }
      if (errors.length) failures.push(`${fixture.format}: ${errors.join(" | ")}`);
      results.push({ format: fixture.format, coverage: drawn });
      if (args.out) {
        fs.mkdirSync(args.out, { recursive: true });
        fs.writeFileSync(path.join(args.out, `format-${fixture.format}.png`), PNG.sync.write(shot));
      }
    } finally {
      await context.close();
    }
  }
}

async function configureScene(page, setting) {
  await page.getByRole("button", { name: "Appearance", exact: true }).click();
  await page.getByRole("menuitemradio", { name: setting.appearance, exact: true }).click();
  if (setting.render) {
    await page.getByRole("button", { name: /^Viewing mode:/ }).click();
    await page.getByRole("menuitemradio", { name: "Render", exact: true }).click();
  }
}

function meanRgb(png) {
  const total = [0, 0, 0];
  for (let i = 0; i < png.data.length; i += 4) {
    total[0] += png.data[i]; total[1] += png.data[i + 1]; total[2] += png.data[i + 2];
  }
  const count = png.data.length / 4;
  return total.map((value) => value / count);
}

function patchMean(png, x0, y0, width, height) {
  const total = [0, 0, 0];
  let count = 0;
  for (let y = Math.max(0, y0); y < Math.min(png.height, y0 + height); y += 1) {
    for (let x = Math.max(0, x0); x < Math.min(png.width, x0 + width); x += 1) {
      const offset = (y * png.width + x) * 4;
      total[0] += png.data[offset]; total[1] += png.data[offset + 1]; total[2] += png.data[offset + 2];
      count += 1;
    }
  }
  return count ? total.map((value) => value / count) : [0, 0, 0];
}

function rgbDistance(a, b) {
  return Math.max(...a.map((value, index) => Math.abs(value - b[index])));
}

async function sceneGates() {
  const settings = [
    { id: "cad-light", appearance: "Light", render: false },
    { id: "cad-dark", appearance: "Dark", render: false },
    { id: "render-light", appearance: "Light", render: true },
    { id: "render-dark", appearance: "Dark", render: true },
  ];
  const sceneMeans = [];
  for (const setting of settings) {
    const { context, page, errors } = await newPage();
    try {
      await openFile(page, "smoke.step");
      await configureScene(page, setting);
      // Inspect's grid stays pinned to world z=0; Render's photographic floor
      // follows the model down to its lowest point by default.
      await page.waitForFunction(
        (follows) => window.__cadModelPlacement?.floorFollowsModel === follows,
        setting.render,
        { timeout: 30_000 },
      );
      const placement = await page.evaluate(() => window.__cadModelPlacement);
      if (!placement) failures.push(`${setting.id}: placement seam absent`);
      else {
        for (let axis = 0; axis < 3; axis += 1) {
          if (Math.abs(Number(placement.position[axis])) > 1e-9) failures.push(`${setting.id}: model moved to [${placement.position}]`);
          if (Math.abs(Number(placement.boundsMin[axis]) - expectedBounds.min[axis]) > 1e-4
              || Math.abs(Number(placement.boundsMax[axis]) - expectedBounds.max[axis]) > 1e-4) {
            failures.push(`${setting.id}: authored bounds changed: [${placement.boundsMin}]..[${placement.boundsMax}]`);
            break;
          }
        }
        if (!setting.render && Math.abs(Number(placement.gridFloorZ)) > 1e-4) {
          failures.push(`${setting.id}: inspection grid left world z=0 (${placement.gridFloorZ})`);
        }
        if (placement.floorFollowsModel !== setting.render) {
          failures.push(`${setting.id}: floor follow is ${placement.floorFollowsModel}, expected ${setting.render}`);
        }
        if (setting.render && Math.abs(Number(placement.groundZ) - expectedBounds.min[2]) > 1e-4) {
          failures.push(`${setting.id}: Render floor sits at ${placement.groundZ}, not the model's lowest point `
            + `(${expectedBounds.min[2]})`);
        }
      }
      if (errors.length) failures.push(`${setting.id}: ${errors.join(" | ")}`);
    } finally {
      await context.close();
    }

    const themed = await newPage();
    try {
      const canvas = await openFile(themed.page, "smoke.stl");
      await configureScene(themed.page, setting);
      await themed.page.waitForTimeout(1000);
      const box = await canvas.boundingBox();
      const clip = {
        x: Math.round(box.x + box.width * 0.20), y: Math.round(box.y + box.height * 0.20),
        width: Math.round(box.width * 0.55), height: Math.round(box.height * 0.60),
      };
      const shot = PNG.sync.read(await themed.page.screenshot({ clip }));
      sceneMeans.push({ id: setting.id, mean: meanRgb(shot) });
      if (themed.errors.length) failures.push(`theme/${setting.id}: ${themed.errors.join(" | ")}`);
    } finally {
      await themed.context.close();
    }
  }
  let spread = 0;
  for (const a of sceneMeans) for (const b of sceneMeans) spread = Math.max(spread, rgbDistance(a.mean, b.mean));
  const renderLight = sceneMeans.find(({ id }) => id === "render-light");
  const renderDark = sceneMeans.find(({ id }) => id === "render-dark");
  const studioSpread = rgbDistance(renderLight.mean, renderDark.mean);
  if (spread <= 4) failures.push(`CAD/Render scene settings did not change the framebuffer (spread ${spread.toFixed(1)})`);
  if (studioSpread <= 4) failures.push(`Light/Dark Render backdrops are visually identical (${studioSpread.toFixed(1)})`);
  await belowOriginGroundGate();
  console.log(`  placement: authored [39,-3,-5]..[45,3,9], inspection grid at world z=0, `
    + `Render floor under the model at z=${expectedBounds.min[2]}`);
  console.log(`  scenes: overall framebuffer spread ${spread.toFixed(1)}/255, Render backdrop spread ${studioSpread.toFixed(1)}/255`);
}

// A robot whose base link origin sits above its lowest geometry. The floor
// used to be pinned to that origin, so the clamp hanging below it was drawn
// behind a backdrop-coloured plane and the render read as cut off at the
// bottom. The default floor is now the model's lowest point, and this holds
// both halves of that: where the plane sits, and that the lowest rows of the
// model still reach the framebuffer as MODEL rather than as floor.
async function belowOriginGroundGate() {
  const { context, page, errors } = await newPage();
  try {
    const canvas = await openFile(page, "below-origin.urdf");
    await configureScene(page, { appearance: "Light", render: true });
    await page.waitForFunction(
      () => window.__cadModelPlacement?.floorFollowsModel === true
        && Number.isFinite(Number(window.__cadModelPlacement?.groundZ)),
      null,
      { timeout: 30_000 },
    );
    const placement = await page.evaluate(() => window.__cadModelPlacement);
    const lowest = Number(placement.boundsMin[2]);
    if (!(lowest < -0.05)) {
      failures.push(`below-origin ground: the fixture is not below its own origin (min z ${lowest})`);
    }
    if (Math.abs(Number(placement.groundZ) - lowest) > 1e-6) {
      failures.push(`below-origin ground: the floor sits at ${placement.groundZ}, not the model's lowest point (${lowest})`);
    }

    // The 3D area only: the canvas runs under the Studio panel, whose pixels
    // never change and would dilute every mean.
    const box = await canvas.boundingBox();
    const clip = {
      x: Math.round(box.x), y: Math.round(box.y),
      width: Math.round(box.width * 0.7), height: Math.round(box.height),
    };
    const shoot = async (name) => {
      const png = PNG.sync.read(await page.screenshot({ clip }));
      if (args.out) {
        fs.mkdirSync(args.out, { recursive: true });
        fs.writeFileSync(path.join(args.out, `ground-below-origin-${name}.png`), PNG.sync.write(png));
      }
      return png;
    };
    const lowestFloor = await shoot("lowest");

    // The previous default, chosen the way a user chooses it.
    await page.getByRole("combobox", { name: "Ground position", exact: true }).click();
    await page.getByRole("option", { name: "Model origin", exact: true }).click();
    await page.waitForFunction(
      () => Math.abs(Number(window.__cadModelPlacement?.groundZ)) < 1e-9,
      null,
      { timeout: 30_000 },
    );
    await page.waitForTimeout(800);
    const originFloor = await shoot("origin");

    const backdrop = patchMean(lowestFloor, 0, 0, 12, 12);
    const rgbAt = (png, offset) => [png.data[offset], png.data[offset + 1], png.data[offset + 2]];
    // Every pixel the model draws with the floor under it. Those same pixels are
    // what a floor at the origin veils: the plane is translucent, so the model
    // is not erased, it is washed toward the backdrop until the shot reads as
    // cut off at the bottom.
    let modelPixels = 0;
    let drawnContrast = 0;
    let veiledContrast = 0;
    let veiled = 0;
    let lowestModelRow = -1;
    for (let y = 0; y < lowestFloor.height; y += 1) {
      for (let x = 0; x < lowestFloor.width; x += 1) {
        const offset = (y * lowestFloor.width + x) * 4;
        const drawn = rgbAt(lowestFloor, offset);
        const contrast = rgbDistance(drawn, backdrop);
        if (contrast <= 24) continue;
        const veiledPixel = rgbAt(originFloor, offset);
        modelPixels += 1;
        drawnContrast += contrast;
        veiledContrast += rgbDistance(veiledPixel, backdrop);
        if (rgbDistance(drawn, veiledPixel) > 12) veiled += 1;
        lowestModelRow = y;
      }
    }
    if (modelPixels < 2000) {
      failures.push(`below-origin ground: the model is barely drawn (${modelPixels} px)`);
    } else {
      const drawnMean = drawnContrast / modelPixels;
      const veiledMean = veiledContrast / modelPixels;
      const veiledFraction = veiled / modelPixels;
      if (!(drawnMean > veiledMean + 4)) {
        failures.push(`below-origin ground: the model reads no better under the default floor than under one at `
          + `the origin (${drawnMean.toFixed(1)} vs ${veiledMean.toFixed(1)} from the backdrop)`);
      }
      if (!(veiledFraction > 0.08)) {
        failures.push(`below-origin ground: a floor at the origin changed only ${(veiledFraction * 100).toFixed(1)}% `
          + `of the model's pixels, so this fixture does not exercise the cut-off`);
      }
      if (lowestModelRow < lowestFloor.height * 0.5) {
        failures.push(`below-origin ground: the model's lowest drawn row is ${lowestModelRow} of ${lowestFloor.height}`);
      }
      console.log(`  below-origin: floor at z=${Number(placement.groundZ).toFixed(3)} (model min ${lowest.toFixed(3)}), `
        + `model reads ${drawnMean.toFixed(1)}/255 from the backdrop down to row ${lowestModelRow}; `
        + `a floor at the origin veils ${(veiledFraction * 100).toFixed(0)}% of it, to ${veiledMean.toFixed(1)}`);
    }
    if (errors.length) failures.push(`below-origin ground: ${errors.join(" | ")}`);
  } finally {
    await context.close();
  }
}

async function qualityGate() {
  const { context, page, errors } = await newPage();
  const state = () => page.evaluate(() => ({
    lod: window.__cadViewportLod?.(),
    quality: window.__cadViewerQuality,
    badge: document.querySelector("[data-file-status]")?.dataset.fileStatus,
  }));
  async function settled(expected) {
    await page.waitForFunction((qualityName) => {
      const lod = window.__cadViewportLod?.();
      const quality = window.__cadViewerQuality;
      return lod?.componentCount > 0 && lod.quality === qualityName && lod.qualitySettled
        && quality?.quality === qualityName && quality.standardQualityReady
        && (qualityName !== "high" || quality.highQualityReady);
    }, expected, { timeout: 60_000 });
    const current = await state();
    if (current.badge) fail(`quality ${expected}: stale file badge ${current.badge}`);
    return current;
  }
  async function mode(current, next) {
    await page.getByRole("button", { name: `Viewing mode: ${current}`, exact: true }).click();
    await page.getByRole("menuitemradio", { name: next, exact: true }).click();
  }
  try {
    await openFile(page, "smoke.step");
    await settled("interactive");
    for (let cycle = 0; cycle < 2; cycle += 1) {
      await mode("Inspect", "Render");
      await settled("high");
      for (const [label, expected] of [["Preview", "standard"], ["Final", "high"]]) {
        await page.getByRole("combobox", { name: "Quality", exact: true }).click();
        await page.getByRole("option", { name: label, exact: true }).click();
        await settled(expected);
      }
      await page.mouse.move(420, 400);
      await page.mouse.down();
      await page.mouse.move(600, 460, { steps: 12 });
      await page.mouse.up();
      await settled("high");
      await mode("Render", "Inspect");
      await settled("interactive");
    }
    if (errors.length) fail(`quality transitions: ${errors.join(" | ")}`);
    console.log("  quality: Inspect/Render, Preview/Final, orbit, and return-to-Inspect settled twice without a stale badge");
  } catch (error) {
    console.error(JSON.stringify(await state()));
    throw error;
  } finally {
    await context.close();
  }
}

// --- robot kinematics ------------------------------------------------------
// The shoulder's FK, as the renderer must place it: the child link's own
// matrix is T(0,0,0.06) * Ry(angle). Column-major, like Matrix4.toArray().
const ARM_JOINT_HEIGHT = 0.06;
const IDENTITY_MATRIX = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
function shoulderFk(angleDeg) {
  const angle = (angleDeg * Math.PI) / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  return [cos, 0, -sin, 0, 0, 1, 0, 0, sin, 0, cos, 0, 0, 0, ARM_JOINT_HEIGHT, 1];
}

function matrixDistance(actual, expected) {
  if (!Array.isArray(actual) || actual.length !== 16) return Number.POSITIVE_INFINITY;
  return Math.max(...expected.map((value, index) => Math.abs(Number(actual[index]) - value)));
}

async function recordMatrix(page, partId) {
  return page.evaluate((id) => {
    const records = window.__cadDisplayRecords?.() || [];
    return records.find((record) => record.partId === id)?.matrix || null;
  }, partId);
}

// Poll rather than assert once: a joint edit and a group state both animate to
// their target over a few frames.
async function settledArmMatrix(page, angleDeg, what, tolerance = 1e-5) {
  const expected = shoulderFk(angleDeg);
  try {
    await page.waitForFunction(({ want, epsilon }) => {
      const record = (window.__cadDisplayRecords?.() || []).find((row) => row.partId === "arm:v1");
      const matrix = record?.matrix;
      return Array.isArray(matrix) && matrix.every((value, index) => Math.abs(value - want[index]) <= epsilon);
    }, { want: expected, epsilon: tolerance }, { timeout: 15_000 });
  } catch {
    const actual = await recordMatrix(page, "arm:v1");
    failures.push(`${what}: arm link renders at [${(actual || []).map((v) => Number(v).toFixed(4))}], `
      + `expected FK [${expected.map((v) => v.toFixed(4))}]`);
    return false;
  }
  return true;
}

// --- camera grounding -----------------------------------------------------
// The camera is fitted ONCE per model, to its zero pose, and no pose change may
// move it: not a joint, not a group state, not a STEP mate, and not the explicit
// Reset view, which re-fits to that same zero pose. The tolerance is only there
// for the last-bit drift OrbitControls' own update leaves behind (observed at
// ~1e-15 relative); the regression this catches moved the framing by 2.4% and
// the pivot by a quarter of the model.
const CAMERA_EPSILON = 1e-9;

async function cameraState(page) {
  return page.evaluate(() => window.__cadCamera?.() || null);
}

function cameraDrift(actual, expected) {
  if (!actual || !expected || !Array.isArray(actual.position) || !Array.isArray(actual.target)) {
    return Number.POSITIVE_INFINITY;
  }
  if (actual.projection !== expected.projection) {
    return Number.POSITIVE_INFINITY;
  }
  const pairs = [
    ...actual.position.map((value, index) => [value, expected.position[index]]),
    ...actual.target.map((value, index) => [value, expected.target[index]]),
    [actual.zoom, expected.zoom],
    // The half-height belongs to the orthographic frustum. The seam reports the
    // runtime's orthographic camera even while the perspective one is active,
    // where it describes no frame that is on screen.
    ...(actual.projection === "orthographic" ? [[actual.halfHeight || 0, expected.halfHeight || 0]] : []),
    [actual.zoomPercent, expected.zoomPercent],
  ];
  return Math.max(...pairs.map(([a, b]) => Math.abs(Number(a) - Number(b)) / Math.max(1, Math.abs(Number(b)))));
}

function describeCamera(camera) {
  if (!camera) return "no camera";
  return `pos [${camera.position.map((v) => v.toFixed(4))}] target [${camera.target.map((v) => v.toFixed(4))}] `
    + `halfHeight ${Number(camera.halfHeight || 0).toFixed(6)} zoom ${camera.zoomPercent.toFixed(2)}%`;
}

async function cameraHeld(page, zeroPose, what) {
  const camera = await cameraState(page);
  const drift = cameraDrift(camera, zeroPose);
  if (!(drift <= CAMERA_EPSILON)) {
    failures.push(`${what}: the camera moved (${drift.toExponential(2)} relative) — ${describeCamera(camera)}, `
      + `zero pose was ${describeCamera(zeroPose)}`);
    return false;
  }
  return true;
}

async function resetView(page) {
  await page.getByRole("button", { name: /Reset view/i }).first().click();
  await page.waitForTimeout(1_500);
}

// --- the camera each mode opens at ----------------------------------------
// Inspect and Render are two cameras. Each fits the model's zero pose itself,
// every time it is entered, so a switch never inherits the other mode's pose
// and zoom -- which is what used to open Render inside the model, or Inspect at
// a perspective distance read as an orthographic frame. A view the user framed
// by hand still stands within its own mode; it simply does not follow them
// across the switch, because switching IS the reset.
async function switchMode(page, current, next) {
  await page.getByRole("button", { name: `Viewing mode: ${current}`, exact: true }).click();
  await page.getByRole("menuitemradio", { name: next, exact: true }).click();
  const projection = next === "Render" ? "perspective" : "orthographic";
  await page.waitForFunction(
    (want) => window.__cadCamera?.()?.projection === want,
    projection,
    { timeout: 60_000 },
  );
  // The fit lands in the scene sync that follows the new renderer.
  await page.waitForTimeout(1_500);
}

async function orbitAndZoom(page) {
  const box = await page.locator("canvas").first().boundingBox();
  const x = Math.round(box.x + box.width * 0.4);
  const y = Math.round(box.y + box.height * 0.5);
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 180, y + 70, { steps: 12 });
  await page.mouse.up();
  await page.mouse.move(x, y);
  await page.mouse.wheel(0, -420);
  await page.waitForTimeout(1_500);
}

async function cameraMoved(page, from, what) {
  const camera = await cameraState(page);
  if (cameraDrift(camera, from) <= 1e-6) {
    failures.push(`${what}: the camera did not move — ${describeCamera(camera)}`);
    return null;
  }
  return camera;
}

async function modeCameraGate() {
  const { context, page, errors } = await newPage();
  try {
    await openFile(page, "smoke.step");
    const inspectFit = await cameraState(page);
    if (inspectFit?.projection !== "orthographic") {
      failures.push(`mode camera: Inspect did not open orthographic (${inspectFit?.projection})`);
    }

    await switchMode(page, "Inspect", "Render");
    const renderFit = await cameraState(page);
    if (!renderFit) failures.push("mode camera: the camera seam published nothing in Render");

    await switchMode(page, "Render", "Inspect");
    await cameraHeld(page, inspectFit, "returning to Inspect");

    // A view taken by hand: it stands in Inspect, and stops at the switch.
    await orbitAndZoom(page);
    const handFramed = await cameraMoved(page, inspectFit, "orbit and zoom in Inspect");
    if (handFramed) {
      await switchMode(page, "Inspect", "Render");
      await cameraHeld(page, renderFit, "Render after a hand-framed Inspect view");
      await orbitAndZoom(page);
      await cameraMoved(page, renderFit, "orbit and zoom in Render");
      await switchMode(page, "Render", "Inspect");
      await cameraHeld(page, inspectFit, "Inspect after a hand-framed Render view");
    }

    // A different model is framed against ITS zero pose, not the camera the
    // last one was left at. Reset view re-fits, so a fresh fit does not move.
    await openFile(page, "assembly.step");
    const assemblyFit = await cameraState(page);
    if (cameraDrift(assemblyFit, inspectFit) <= 1e-3) {
      failures.push(`mode camera: a different model opened at the previous model's frame — ${describeCamera(assemblyFit)}`);
    }
    await resetView(page);
    await cameraHeld(page, assemblyFit, "a newly opened model");
    await switchMode(page, "Inspect", "Render");
    const assemblyRenderFit = await cameraState(page);
    if (cameraDrift(assemblyRenderFit, renderFit) <= 1e-3) {
      failures.push(`mode camera: Render reopened at the previous model's photographic frame — `
        + `${describeCamera(assemblyRenderFit)}`);
    }
    if (errors.length) failures.push(`mode camera: ${errors.join(" | ")}`);
    console.log(`  mode camera: Inspect ${describeCamera(inspectFit)}`);
    console.log(`  mode camera: Render  ${describeCamera(renderFit)}`);
    console.log("  mode camera: every switch re-fits the mode being entered to the zero pose, "
      + "a hand-framed view stays in its own mode, and a new model is framed against its own box");
  } finally {
    await context.close();
  }
}

async function kinematicsGate() {
  const { context, page, errors } = await newPage();
  try {
    await openFile(page, "smoke.urdf");
    const records = await page.evaluate(() => window.__cadDisplayRecords?.() || []);
    if (records.length !== 2) {
      failures.push(`urdf kinematics: expected one record per link, saw ${records.length}`);
    }
    // Rest pose: the child link sits at its joint origin, not piled on the root.
    const base = await recordMatrix(page, "base:v1");
    if (matrixDistance(base, IDENTITY_MATRIX) > 1e-6) {
      failures.push(`urdf kinematics: root link is not at the robot origin [${base}]`);
    }
    await settledArmMatrix(page, 0, "urdf rest pose");
    // The framing the model opened at. Every assertion below is against THIS.
    const zeroPoseCamera = await cameraState(page);
    if (!zeroPoseCamera) failures.push("urdf kinematics: the camera seam published nothing");

    // The user's control, not the data behind it: type into the joint's value box.
    const valueBox = page.getByRole("textbox", { name: "shoulder value in deg", exact: true });
    await valueBox.waitFor({ timeout: 15_000 });
    await valueBox.click();
    await valueBox.fill("45");
    await valueBox.press("Enter");
    await settledArmMatrix(page, 45, "urdf joint value entry");
    await cameraHeld(page, zeroPoseCamera, "urdf joint value entry");

    // And the slider itself, which commits through the scrub path. The Joints
    // section is the only open one for a robot, so it owns the only slider.
    const sliders = page.locator('[data-slot="slider"]');
    const sliderCount = await sliders.count();
    if (sliderCount !== 1) {
      failures.push(`urdf kinematics: expected the shoulder to be the only slider, saw ${sliderCount}`);
    } else {
      const box = await sliders.first().boundingBox();
      await page.mouse.click(box.x + box.width * 0.25, box.y + box.height / 2);
      await page.waitForTimeout(1500);
      const shown = await valueBox.inputValue();
      const scrubbed = Number.parseFloat(String(shown).replace(/[^\d.+-]/g, ""));
      if (!Number.isFinite(scrubbed) || Math.abs(scrubbed - 45) < 1) {
        failures.push(`urdf kinematics: dragging the slider did not change the joint value (${shown})`);
      } else {
        await settledArmMatrix(page, scrubbed, `urdf joint slider (${shown})`, 2e-3);
        await cameraHeld(page, zeroPoseCamera, `urdf joint slider (${shown})`);
      }
    }
    // Reset view is the one control that re-fits, and it re-fits to the zero
    // pose -- not to the arm where the slider left it.
    await resetView(page);
    await cameraHeld(page, zeroPoseCamera, "urdf reset view while posed");
    if (errors.length) failures.push(`urdf kinematics: ${errors.join(" | ")}`);
  } finally {
    await context.close();
  }

  const srdf = await newPage();
  try {
    await openFile(srdf.page, "smoke.srdf");
    await settledArmMatrix(srdf.page, 0, "srdf rest pose");
    const srdfZeroPoseCamera = await cameraState(srdf.page);
    const groupState = srdf.page.getByRole("combobox", { name: "Group state", exact: true });
    await groupState.waitFor({ timeout: 15_000 });
    await groupState.click();
    await srdf.page.getByRole("option", { name: "lifted", exact: true }).click();
    // The SRDF group state is authored in radians.
    await settledArmMatrix(srdf.page, (0.5 * 180) / Math.PI, "srdf group state");
    await cameraHeld(srdf.page, srdfZeroPoseCamera, "srdf group state");
    if (srdf.errors.length) failures.push(`srdf kinematics: ${srdf.errors.join(" | ")}`);
  } finally {
    await srdf.context.close();
  }

  // The other half of the contract: a STEP document posed by its sidecar's
  // mates, which reaches the scene as cadScene parameters rather than as a
  // posed mesh wrapper. Swinging this arm 90 degrees rewrites the model's
  // bounding box, so a camera fitted to the live pose lands somewhere else
  // entirely -- before this was grounded, Reset view moved the pivot from
  // [24, 0, 3] to [0, 24, 3].
  const hinge = await newPage();
  try {
    await openFile(hinge.page, "hinge.step");
    const hingeZeroPoseCamera = await cameraState(hinge.page);
    if (!hingeZeroPoseCamera) failures.push("step kinematics: the camera seam published nothing");
    await hinge.page.getByRole("tab", { name: "Kinematics", exact: true }).click();
    const swing = hinge.page.getByRole("textbox", { name: /^swing/ }).first();
    await swing.waitFor({ timeout: 15_000 });
    await swing.click();
    await swing.fill("90");
    await swing.press("Enter");
    const swung = await hinge.page.waitForFunction(() => {
      const record = (window.__cadDisplayRecords?.() || []).find((row) => row.partId === "o1.2");
      // A 90 degree swing about +Z carries the arm's +30 X offset onto +Y.
      return Array.isArray(record?.matrix) && Math.abs(record.matrix[13] - 30) < 1e-3;
    }, null, { timeout: 15_000 }).then(() => true).catch(() => false);
    if (!swung) {
      failures.push("step kinematics: the swing mate did not move the arm occurrence");
    } else {
      await cameraHeld(hinge.page, hingeZeroPoseCamera, "step mate value entry");
      await resetView(hinge.page);
      await cameraHeld(hinge.page, hingeZeroPoseCamera, "step reset view while posed");
    }

    // A pose must not re-frame; a REVISION must. Saving a rebuilt model over the
    // open one gives it a new zero pose, and a camera still fitted to the old one
    // leaves the new geometry clipped outside the frame. The grown arm reaches
    // x = 158 where the first revision stopped at 58, so the old frame cannot
    // contain it.
    for (const name of ["hinge.step", "hinge.step.json"]) {
      fs.copyFileSync(path.join(root, ".revision", name), path.join(root, name));
    }
    const grown = await hinge.page.waitForFunction(() => {
      const placement = window.__cadModelPlacement;
      return Number(placement?.boundsMax?.[0]) > 100;
    }, null, { timeout: 60_000 }).then(() => true).catch(() => false);
    if (!grown) {
      failures.push("step revision: the viewer never picked up the rebuilt model");
    } else {
      // Settle: the fit lands in the same effect that adopts the new geometry.
      await hinge.page.waitForTimeout(1_500);
      const revised = await cameraState(hinge.page);
      if (cameraDrift(revised, hingeZeroPoseCamera) <= CAMERA_EPSILON) {
        failures.push(`step revision: the camera kept the previous revision's frame — ${describeCamera(revised)}`);
      } else if (!(Number(revised?.halfHeight) > Number(hingeZeroPoseCamera?.halfHeight))) {
        failures.push(`step revision: the model grew but the frame did not — ${describeCamera(revised)}, `
          + `was ${describeCamera(hingeZeroPoseCamera)}`);
      } else if (Math.abs(Number(revised?.zoomPercent) - 100) > 0.5) {
        failures.push(`step revision: the new fit does not read as 100% (${revised?.zoomPercent})`);
      }
    }
    if (hinge.errors.length) failures.push(`step kinematics: ${hinge.errors.join(" | ")}`);
  } finally {
    await hinge.context.close();
  }
  console.log("  kinematics: URDF rest FK, joint value entry, joint slider, an SRDF group state and a STEP mate "
    + "all place the child link and none of them move the camera off the zero-pose fit, "
    + "while a saved revision re-fits to its own zero pose");
}

const gates = [
  ["picking", async () => {
    await pickingGate("cold+lod", true);
    await pickingGate("warm+lod", true);
    await pickingGate("lod-off", false);
  }],
  ["pick", () => pickingGate("pick", true, { depth: "smoke" })],
  ["format", formatGate],
  ["scene", sceneGates],
  ["quality", qualityGate],
  ["kinematics", kinematicsGate],
  ["camera", modeCameraGate],
];

// The CI subset: every user-visible flow this suite owns, over the cheapest
// fixtures that still exercise the real path — open a file (one per load path),
// pick a face, drive a joint, switch mode. Nothing here reads a frame rate or
// sleeps toward a conclusion; each assertion settles on published state, so a
// slow software-GL runner is slower, not redder.
//
// What stays MANUAL and why:
//   picking  the edge phase brute-force-clicks for a pixel on the silhouette and
//            scores highlight fragmentation at 1-pixel steps. It is the single
//            most expensive gate here and the most sensitive to how the runner
//            rasterizes a thin line.
//   scene    compares mean luminance between appearance presets and between the
//            Inspect grid and the Render floor. A software rasterizer's tone is
//            its own; these thresholds are calibrated on real GPUs.
//   quality  deterministic, but Inspect/Render/Preview/Final is walked TWICE and
//            re-derives a high-quality tessellation each cycle. It is the first
//            gate to promote if the CI budget grows.
const CI_GATES = ["format", "pick", "kinematics", "camera"];

const selected = args.only
  ? gates.filter(([name]) => name === args.only)
  : (args.ci ? CI_GATES.map((name) => gates.find(([gate]) => gate === name)) : gates);
if (!selected.length) fail(`unknown --only gate: ${args.only} (${gates.map(([name]) => name).join(", ")})`);
try {
  for (const [name, gate] of selected) {
    const startedAt = Date.now();
    await gate();
    console.log(`  [gate ${name}] ${((Date.now() - startedAt) / 1000).toFixed(1)}s`);
  }
} finally {
  await browser.close();
}

for (const result of results) console.log(`  ${result.format.padEnd(5)} framebuffer coverage ${result.coverage.toFixed(4)}`);
if (failures.length) {
  console.error("viewer browser failures:");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`viewer browser e2e: PASS (${selected.map(([name]) => name).join(", ")})`);
