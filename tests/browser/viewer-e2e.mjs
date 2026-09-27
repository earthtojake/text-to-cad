#!/usr/bin/env node
// Real-browser coverage for the bundled Viewer: every load path opens through the
// real backend and bundle, and the camera holds across modes and re-fits a saved
// revision. CI runs all of it; there is no local-only set. Fixture and process
// lifecycle belong to scripts/test/test-viewer-browser.sh.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const { chromium } = createRequire(path.join(REPO, "packages/core/package.json"))("playwright");
const { PNG } = createRequire(path.join(REPO, "apps/web/package.json"))("pngjs");

function parseArgs(argv) {
  const args = { url: "", dir: "", out: "", only: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === "--url") args.url = argv[++i] || "";
    else if (flag === "--dir") args.dir = argv[++i] || "";
    else if (flag === "--out") args.out = argv[++i] || "";
    // One gate at a time while working on it: --only camera.
    else if (flag === "--only") args.only = argv[++i] || "";
    else throw new Error(`unknown argument: ${flag}`);
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const diagnosticDir = args.out || process.env.VIEWER_TEST_DIAGNOSTICS_DIR || "";
const root = path.resolve(args.dir || ".");
// One fixture per LOAD PATH: an exact-surface STEP package, a mesh, a 2D drawing,
// a robot description.
const fixtures = [
  // `tools` is the file's own tool strip (a mesh and a drawing have none: a tool that does not
  // apply is hidden, not disabled); `threeD` has the viewport's Display settings and Preview.
  { format: "stl", file: "smoke.stl", parts: false, tools: [], threeD: true },
  { format: "step", file: "assembly.step", parts: true, tools: ["Select", "Draw", "Measure"], threeD: true },
  // A drawing is line work, not shaded surfaces: its outline covers a fraction of what a solid does.
  { format: "dxf", file: "smoke.dxf", parts: false, tools: [], threeD: false, minCoverage: 0.003 },
  { format: "urdf", file: "smoke.urdf", parts: false, tools: ["Select", "Position"], threeD: true },
];
// Small enough that software WebGL and the PNG encode stay cheap on CI, large enough for the
// layout to be the desktop one.
const viewport = { width: 1024, height: 640 };
const viewerOrigin = args.url ? new URL(args.url).origin : "";
const latestReleaseApiUrl = "https://api.github.com/repos/earthtojake/text-to-cad/releases/latest";
const currentVersion = fs.readFileSync(path.join(REPO, "VERSION"), "utf8").trim();
const failures = [];
const results = [];
const cameraReadiness = new WeakMap();
let activeGate = "setup";

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

async function newPage() {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const errors = [];
  const responseReads = new Set();
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
    // Catalog identities are absolute so two hosted projects can keep separate
    // file state. Artifact/editing endpoints accept the served-root reference.
    if (["/__cad/artifact", "/__cad/preview"].includes(parsed.pathname)) {
      const file = parsed.searchParams.get("file") || "";
      if (/^(?:[/\\]|[a-z]:[/\\])/i.test(file)) {
        errors.push(`absolute file identity leaked to ${parsed.pathname}: ${file}`);
      }
    }
    if (["http:", "https:"].includes(parsed.protocol) && parsed.origin !== viewerOrigin) {
      errors.push(`unexpected external request: ${request.method()} ${url} (${request.resourceType()})`);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30_000);
  page.on("response", response => {
    if (response.status() < 400 || !response.url().startsWith(`${viewerOrigin}/__cad/`)) return;
    const read = response.text().then(body => {
      const request = response.request();
      const payload = request.postData();
      const detail = `HTTP ${response.status()} ${request.method()} ${response.url()}: ${body.slice(0, 2000)}`
        + (payload ? `; request: ${payload.slice(0, 4000)}` : "");
      errors.push(detail);
      console.error(`  [gate ${activeGate}] ${detail}`);
    }).catch(() => {});
    responseReads.add(read);
    void read.finally(() => responseReads.delete(read));
  });
  page.on("pageerror", (error) => errors.push(`page: ${error.message || error}`));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const location = message.location();
    const source = location.url
      ? ` at ${location.url}:${Number(location.lineNumber) + 1}:${Number(location.columnNumber) + 1}`
      : "";
    errors.push(`console: ${message.text()}${source}`);
  });
  await page.addInitScript(MODEL_BOUNDS_SCRIPT);
  await page.addInitScript(() => {
    window.__viewerTestCameraLodTrace = [];
    window.addEventListener("cad:lod-status", (event) => {
      const status = event.detail;
      const trace = window.__viewerTestCameraLodTrace;
      trace.push({ at: performance.now(), camera: window.__cadCamera?.(), pending: status?.pendingEvaluation,
        occupied: status?.occupied, settled: status?.qualitySettled });
      if (trace.length > 8) trace.shift();
    });
  });
  // Keep one bounded diagnostic snapshot per gate. It is written before the
  // owned context closes, so a thrown assertion still leaves its actual UI and
  // renderer state available instead of only a locator timeout.
  const closeContext = context.close.bind(context);
  context.close = async () => {
    let responseTimer;
    try {
      await Promise.race([Promise.all([...responseReads]), new Promise(resolve => { responseTimer = setTimeout(resolve, 3000); })]);
    } finally { clearTimeout(responseTimer); }
    if (diagnosticDir && !page.isClosed()) {
      fs.mkdirSync(diagnosticDir, { recursive: true });
      const stem = path.join(diagnosticDir, `diagnostic-${activeGate}`);
      let timer;
      let stateWritten = false;
      try {
        const state = await Promise.race([
          page.evaluate(() => ({
            url: location.href,
            text: document.body.innerText.slice(0, 24000),
            buttons: [...document.querySelectorAll('button')].filter(node => node.getBoundingClientRect().height).map(node => ({ label: node.getAttribute('aria-label'), text: node.innerText.slice(0, 120), disabled: node.disabled })).slice(0, 120),
            placement: window.__cadModelPlacement,
            canvases: [...document.querySelectorAll('canvas')].map(canvas => canvas.getBoundingClientRect().toJSON()),
            camera: window.__cadCamera?.(),
            cameraLodTrace: window.__viewerTestCameraLodTrace,
            lod: window.__cadViewportLod?.(),
            quality: window.__cadViewerQuality,
            badge: document.querySelector('[data-file-status]')?.dataset.fileStatus,
          })),
          new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('diagnostic state timed out')), 3000); }),
        ]);
        fs.writeFileSync(`${stem}.json`, JSON.stringify({ ...state, cameraReadiness: cameraReadiness.get(page), errors: errors.slice(-15).map(error => error.slice(0, 2500)) }, null, 2));
        stateWritten = true;
        if (args.out) await page.screenshot({ path: `${stem}.png`, timeout: 3000 });
      } catch (error) {
        console.error(`  diagnostic ${activeGate}: ${error.message}`);
        if (!stateWritten) {
          fs.writeFileSync(`${stem}.json`, JSON.stringify({
            url: page.url(), diagnosticError: error.message, cameraReadiness: cameraReadiness.get(page),
            errors: errors.slice(-15).map(error => error.slice(0, 2500)),
          }, null, 2));
        }
      } finally { clearTimeout(timer); }
    }
    return closeContext();
  };
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
  // The file's viewer is mounted: every renderer draws into one `data-slot="cad-file-view"` frame,
  // and its viewport says when it has what it was loading (`aria-busy="false"`).
  await page.locator('[data-slot="cad-file-view"]').first().waitFor({ timeout: 60_000 });
  const canvas = page.locator("canvas").first();
  await canvas.waitFor({ state: "visible", timeout: 60_000 });
  await page.locator('[data-slot="cad-file-view"] [aria-busy="false"]').first().waitFor({ timeout: 120_000 });
  // Then settle on the seam that says the model reached the RENDERER, not on a second of wall
  // clock: every 3D renderer's viewport publishes the bounds it staged (`modelBounds`); a 2D
  // drawing has none, and its viewport's `aria-busy` is the whole of it. The short pause after it
  // is for the frame to be painted, which has no seam of its own.
  if (!/\.dxf$/i.test(file)) {
    await page.waitForFunction(() => {
      const bounds = window.__cadModelBounds?.();
      return Array.isArray(bounds?.min) && Array.isArray(bounds?.max)
        && bounds.min.some((value, axis) => Number(bounds.max[axis]) - Number(value) > 0);
    }, null, { timeout: 120_000 });
  }
  await page.waitForTimeout(250);
  return canvas;
}

/** The staged model's bounds, from whichever seam its renderer publishes. */
const MODEL_BOUNDS_SCRIPT = () => {
  window.__cadModelBounds = () => {
    const placement = window.__cadModelPlacement;
    if (Array.isArray(placement?.boundsMin)) return { min: placement.boundsMin, max: placement.boundsMax };
    const stage = window.__cadStage?.();
    return stage?.bounds ? { min: stage.bounds.min, max: stage.bounds.max } : null;
  };
};

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
  // Framing lives in STEP's viewport menu and nowhere else: no other renderer opens a
  // viewport menu at all, and the Inspector's zoom readout and its menu are gone.
  const framing = ["Zoom to fit", "Zoom to selection"];
  const presentTree = ["Expand all", "Collapse all"];
  for (const fixture of fixtures) {
    const { context, page, errors } = await newPage();
    try {
      const canvas = await openFile(page, fixture.file);
      const shot = PNG.sync.read(await canvas.screenshot());
      const drawn = coverage(shot);
      if (fixture.threeD) {
        const bounds = await page.evaluate(() => window.__cadModelBounds?.() || null);
        const spans = bounds?.min?.map((value, axis) => Number(bounds.max?.[axis]) - Number(value)) || [];
        if (!spans.some((value) => Number.isFinite(value) && value > 0)) {
          failures.push(`${fixture.format}: no non-empty model bounds reached the renderer`);
        }
      }
      if (drawn < (fixture.minCoverage ?? 0.03)) failures.push(`${fixture.format}: no foreground model region (${drawn.toFixed(4)})`);
      // The file's own tools, exactly: one that does not apply is hidden, not disabled.
      const strip = await page.locator('[role="group"][aria-label="Interaction tools"] button').evaluateAll((buttons) =>
        buttons.map((button) => button.getAttribute("aria-label")));
      for (const label of fixture.tools) if (!strip.includes(label)) failures.push(`${fixture.format}: missing ${label} (strip: ${strip.join(", ")})`);
      if (!fixture.tools.length && strip.length) failures.push(`${fixture.format}: a tool strip on a file with no tools (${strip.join(", ")})`);
      if (!fixture.tools.includes("Measure") && strip.includes("Measure")) {
        failures.push(`${fixture.format}: Measure is offered on a view that cannot measure (must be hidden, not disabled)`);
      }
      // A 3D view's top-right bar: Display settings, then Preview.
      const topRight = await page.locator("[data-viewport-actions] button").evaluateAll((buttons) =>
        buttons.map((button) => button.getAttribute("aria-label")));
      if (fixture.threeD && JSON.stringify(topRight) !== JSON.stringify(["Display settings", "Preview"])) {
        failures.push(`${fixture.format}: top-right bar is ${JSON.stringify(topRight)}`);
      }
      // Every file can be captured from the navigation row.
      const snapshot = page.getByRole("button", { name: "Take snapshot", exact: true });
      if (!(await snapshot.count()) || !(await snapshot.first().isEnabled())) failures.push(`${fixture.format}: missing or disabled Take snapshot`);
      const menu = await canvasMenuItems(page, canvas);
      if (fixture.parts) {
        for (const item of framing) if (!menu.includes(item)) failures.push(`${fixture.format}: menu missing ${item}`);
        for (const item of presentTree) if (!menu.includes(item)) failures.push(`${fixture.format}: parts menu missing ${item}`);
      } else if (menu.length) {
        failures.push(`${fixture.format}: a viewport menu opened on a renderer that has none (${menu.join(", ")})`);
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

// Inspect and Render are the Display settings' Solid and Render presets, chosen from the Mode
// dropdown of the popover the viewport's top-right bar opens.
const VIEWING_PRESET = { Inspect: "Solid", Render: "Render" };
async function selectViewingMode(page, current, next) {
  const popover = page.locator("[data-display-popover]");
  if (!(await popover.count())) await page.getByRole("button", { name: "Display settings", exact: true }).click();
  const mode = popover.getByRole("combobox", { name: "Mode", exact: true });
  await mode.waitFor();
  if ((await mode.innerText()).trim() !== VIEWING_PRESET[current]) fail(`viewing mode: expected ${current} before switching to ${next}`);
  await mode.click();
  await page.getByRole("option", { name: VIEWING_PRESET[next], exact: true }).click();
  await page.waitForFunction((label) => document.querySelector('[data-display-popover] [role="combobox"][aria-label="Mode"]')?.textContent.trim() === label,
    VIEWING_PRESET[next]);
  await page.keyboard.press("Escape");
  await popover.waitFor({ state: "detached" });
}

// --- camera grounding -----------------------------------------------------
// The camera is fitted ONCE per model, to its zero pose: a mode round trip does
// not move it, the explicit Reset view re-fits to that same zero pose, and only a
// saved REVISION (a new zero pose) re-fits it. The tolerance is only there for
// the last-bit drift OrbitControls' own update leaves behind (observed at ~1e-15
// relative); the regression this catches moved the framing by 2.4% and the pivot
// by a quarter of the model.
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
  // An orthographic picture does not depend on how far back along its line of sight the camera
  // stands, only on which way it looks: its direction is compared, not its position.
  const direction = (camera) => {
    const offset = camera.position.map((value, index) => Number(value) - Number(camera.target[index]));
    const length = Math.hypot(...offset) || 1;
    return offset.map((value) => value / length);
  };
  const where = actual.projection === "orthographic"
    ? direction(actual).map((value, index) => [value, direction(expected)[index]])
    : actual.position.map((value, index) => [value, expected.position[index]]);
  const pairs = [
    ...where,
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

// Reset view is the viewport menu's Zoom to fit: the model framed again, the camera not turned.
// Only a renderer with a viewport menu (STEP) offers it, and only under Select, whose menu it is.
async function resetView(page) {
  await page.getByRole("button", { name: "Select", exact: true }).click();
  const box = await page.locator("canvas").first().boundingBox();
  await page.mouse.click(box.x + box.width * 0.12, box.y + box.height * 0.86, { button: "right" });
  await page.getByRole("menuitem", { name: "Zoom to fit", exact: true }).click();
  // Reset changes framing on the presented model. The pose and zero-pose
  // camera assertions do not require a queued LOD camera sample to finish;
  // actual geometry adoption, presentation and camera stability still do.
  await settledCameraFrame(page, { stage: "reset view", requireSettledLod: false });
}

// --- the camera across modes ----------------------------------------------
// Inspect (Solid) and Render are Display presets over one view: a switch converts
// the camera to the other projection, keeping what it looks at and how large it
// draws it, and converting back returns the view exactly. A model opens framed
// against its own zero pose.
async function settledCameraFrame(page, { projection = null, stage, requireSettledLod = true, timeout = 60_000 } = {}) {
  const startedAt = Date.now();
  cameraReadiness.set(page, { ...cameraReadiness.get(page), pending: { stage, projection, requireSettledLod } });
  // Projection is published during scene reconciliation, before Render's
  // environment and first frame are necessarily ready. The presentation host
  // clears aria-busy only after drawing that destination scene. Camera damping
  // must settle for every framing assertion; mode/gesture checks also require
  // settled LOD refinement.
  const ready = await page.waitForFunction(({ want, requireSettledLod }) => {
    const read = () => {
      const canvas = document.querySelector("canvas");
      const camera = window.__cadCamera?.();
      const quality = window.__cadViewerQuality;
      const lod = window.__cadViewportLod?.();
      if (!canvas || !camera || (want && camera.projection !== want)
        || canvas.closest("[aria-busy]")?.getAttribute("aria-busy") !== "false"
        || getComputedStyle(canvas).visibility !== "visible"
        || document.querySelector("[data-viewer-transition]")) return null;
      const expectedQualities = camera.projection === "perspective" ? ["standard", "high"] : ["interactive"];
      if (!quality?.standardQualityReady || !expectedQualities.includes(quality.quality)) return null;
      if (lod?.componentCount > 0 && (lod.quality !== quality.quality || lod.busy || lod.collectionPending
        || (requireSettledLod && (!lod.qualitySettled || lod.pendingEvaluation)))) return null;
      return { canvas, camera, quality: quality.quality, levelCounts: lod?.levelCounts,
        lodSettled: lod?.qualitySettled, lodPendingEvaluation: lod?.pendingEvaluation };
    };
    const after = read();
    if (!after) {
      delete window.__viewerTestCameraFrame;
      return false;
    }
    const coordinates = camera => [...camera.position, ...camera.target, ...camera.up, camera.zoom, camera.zoomPercent,
      ...(camera.projection === "orthographic" ? [camera.halfHeight] : [])];
    const before = window.__viewerTestCameraFrame;
    const a = before ? coordinates(before.camera) : [], b = coordinates(after.camera);
    const stable = before?.canvas === after.canvas && before.quality === after.quality
      && a.every((value, index) => Math.abs(value - b[index]) <= 1e-9 * Math.max(1, Math.abs(value)));
    const stableFrames = stable ? before.stableFrames + 1 : 0;
    window.__viewerTestCameraFrame = { ...after, stableFrames };
    if (stableFrames < 2) return false;
    const gl = after.canvas.getContext("webgl2");
    if (!gl || gl.isContextLost()) throw new Error('camera: presented canvas has no live WebGL2 context');
    gl.finish();
    delete window.__viewerTestCameraFrame;
    return { camera: after.camera, quality: after.quality, levelCounts: after.levelCounts,
      lodSettled: after.lodSettled, lodPendingEvaluation: after.lodPendingEvaluation,
      width: after.canvas.width, height: after.canvas.height };
  }, { want: projection, requireSettledLod }, { timeout, polling: "raf" });
  try {
    const state = { stage, waitMs: Date.now() - startedAt, ...await ready.jsonValue() };
    cameraReadiness.set(page, state);
    console.log(`  camera ready: ${JSON.stringify(state)}`);
  } finally {
    await ready.dispose();
  }
}

async function switchMode(page, current, next) {
  const deadline = Date.now() + 60_000;
  await selectViewingMode(page, current, next);
  const projection = next === "Render" ? "perspective" : "orthographic";
  const timeout = deadline - Date.now();
  if (timeout <= 0) fail(`mode camera: ${next} transition exceeded 60s`);
  await settledCameraFrame(page, { projection, stage: `${current} to ${next}`, timeout });
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
  await settledCameraFrame(page, { stage: "orbit and zoom" });
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
    await settledCameraFrame(page, { projection: "orthographic", stage: "initial Inspect frame" });
    const inspectFit = await cameraState(page);
    if (inspectFit?.projection !== "orthographic") {
      failures.push(`mode camera: Inspect did not open orthographic (${inspectFit?.projection})`);
    }

    // Solid and Render are presets over ONE view: a switch converts the camera to the other
    // projection, keeping what it looks at and how large it draws it, and a round trip is exact.
    await switchMode(page, "Inspect", "Render");
    const renderFit = await cameraState(page);
    if (!renderFit) failures.push("mode camera: the camera seam published nothing in Render");
    else if (renderFit.target.some((value, axis) => Math.abs(value - inspectFit.target[axis]) > 1e-6)) {
      failures.push(`mode camera: Render re-aimed the view — ${describeCamera(renderFit)}`);
    }

    await switchMode(page, "Render", "Inspect");
    await cameraHeld(page, inspectFit, "returning to Inspect");

    // A view taken by hand survives a round trip, in either mode.
    await orbitAndZoom(page);
    const handFramed = await cameraMoved(page, inspectFit, "orbit and zoom in Inspect");
    if (handFramed) {
      await switchMode(page, "Inspect", "Render");
      await switchMode(page, "Render", "Inspect");
      await cameraHeld(page, handFramed, "Inspect after a round trip through Render");
      await switchMode(page, "Inspect", "Render");
      await orbitAndZoom(page);
      const renderFramed = await cameraMoved(page, renderFit, "orbit and zoom in Render");
      await switchMode(page, "Render", "Inspect");
      await switchMode(page, "Inspect", "Render");
      if (renderFramed) await cameraHeld(page, renderFramed, "Render after a round trip through Inspect");
      await switchMode(page, "Render", "Inspect");
    }

    // A different model is framed against ITS zero pose, not the camera the
    // last one was left at. Reset view re-fits, so a fresh fit does not move.
    await openFile(page, "assembly.step");
    await settledCameraFrame(page, { projection: "orthographic", stage: "new model Inspect frame" });
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
    console.log("  mode camera: a switch converts the view without re-aiming it, a round trip returns "
      + "the view it started from, and a new model is framed against its own box");
  } finally {
    await context.close();
  }

  // A mode switch or a pose must not re-frame; a REVISION must. Saving a rebuilt
  // model over the open one gives it a new zero pose, and a camera still fitted to
  // the old one leaves the new geometry clipped outside the frame. The grown arm
  // reaches x = 158 where the first revision stopped at 58, so the old frame cannot
  // contain it. A fresh tab, because the re-fit is for a camera nobody chose: one
  // the tab kept for this file (Zoom to fit saves one) is restored instead.
  const revision = await newPage();
  try {
    await openFile(revision.page, "hinge.step");
    const firstFit = await cameraState(revision.page);
    fs.copyFileSync(path.join(root, ".revision", "hinge.step"), path.join(root, "hinge.step"));
    const grown = await revision.page.waitForFunction(() => {
      const bounds = window.__cadModelBounds?.();
      return Number(bounds?.max?.[0]) > 100;
    }, null, { timeout: 60_000 }).then(() => true).catch(() => false);
    if (!grown) {
      failures.push("step revision: the viewer never picked up the rebuilt model");
    } else {
      // Settle: the fit lands in the same effect that adopts the new geometry.
      await revision.page.waitForTimeout(1_500);
      const revised = await cameraState(revision.page);
      if (cameraDrift(revised, firstFit) <= CAMERA_EPSILON) {
        failures.push(`step revision: the camera kept the previous revision's frame — ${describeCamera(revised)}`);
      } else if (!(Number(revised?.halfHeight) > Number(firstFit?.halfHeight))) {
        failures.push(`step revision: the model grew but the frame did not — ${describeCamera(revised)}, `
          + `was ${describeCamera(firstFit)}`);
      } else if (Math.abs(Number(revised?.zoomPercent) - 100) > 0.5) {
        failures.push(`step revision: the new fit does not read as 100% (${revised?.zoomPercent})`);
      }
    }
    if (revision.errors.length) failures.push(`step revision: ${revision.errors.join(" | ")}`);
    console.log("  step revision: a saved revision re-fits a camera nobody moved to its own zero pose");
  } finally {
    await revision.context.close();
  }
}

// Every gate here runs in CI; there is no local-only set. Each assertion settles
// on published state rather than a frame rate or a sleep toward a conclusion, so a
// slow software-GL runner is slower, not redder. Picking parts, faces and robot
// links, and driving URDF joints and STEP mates, belong to the packages/ui browser
// specs.
const gates = [
  ["format", formatGate],
  ["camera", modeCameraGate],
];

const selected = args.only ? gates.filter(([name]) => name === args.only) : gates;
if (!selected.length) fail(`unknown --only gate: ${args.only} (${gates.map(([name]) => name).join(", ")})`);
try {
  for (const [name, gate] of selected) {
    const startedAt = Date.now();
    const failuresBefore = failures.length;
    activeGate = name;
    console.log(`  [gate ${name}] starting`);
    try {
      await gate();
    } catch (error) {
      failures.push(`${name}: ${error.stack || error.message || error}`);
      console.error(`  [gate ${name}] failed: ${error.message || error}`);
    }
    const addedFailures = failures.length - failuresBefore;
    console.log(`  [gate ${name}] ${addedFailures ? `FAIL (${addedFailures})` : "PASS"} ${((Date.now() - startedAt) / 1000).toFixed(1)}s`);
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

