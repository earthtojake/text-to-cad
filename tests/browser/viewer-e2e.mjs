#!/usr/bin/env node
// Real-browser coverage for the bundled Viewer: every load path opens through the
// real backend and bundle, the camera holds across modes, and a saved revision re-fits a
// camera nobody has touched and keeps one the person took. CI runs all of it; there is no
// local-only set. Fixture and process lifecycle belong to scripts/test/test-viewer-browser.sh.

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
// One fixture per LOAD PATH: a mesh, a 2D drawing, a robot description, and the two
// documents the cadgen engine serves -- a STEP and an engine document (.xbf) -- read through
// the viewer and drawn by one renderer.
const fixtures = [
  // `tools` is the file's own tool strip; unavailable tools are hidden. `threeD` has
  // Projection, Display and Preview at the strip's end; `sections`
  // are file sidebar tiles it must have (what there is to read of the file, whatever the tool).
  { format: "stl", file: "smoke.stl", parts: false, tools: ["Pencil", "Shapes", "Clip"], sections: [], threeD: true },
  // A STEP: read by the engine, drawn as an engine document is.
  { format: "step", file: "assembly.step", parts: true, tools: ["Select", "Pencil", "Shapes", "Measure", "Clip"], sections: ["Model tree"], threeD: true },
  // A drawing is line work, not shaded surfaces: its outline covers a fraction of what a solid does.
  { format: "dxf", file: "smoke.dxf", parts: false, tools: ["Select", "Pencil", "Shapes", "Measure"], sections: [], threeD: false, minCoverage: 0.003 },
  { format: "urdf", file: "smoke.urdf", parts: false, tools: ["Select", "Pencil", "Shapes", "Measure", "Clip"], sections: ["Links"], threeD: true },
  // A cadgen engine document: served by the engine, read by the page from it, and picked,
  // measured and laid out as a STEP's is, with a STEP's pick menus on Select's and Measure's chevrons.
  { format: "xbf", file: "smoke.xbf", parts: true,
    tools: ["Select", "Selection filter: everything", "Pencil", "Shapes", "Measure", "Measure filter: everything", "Clip"], sections: ["Model tree"], threeD: true },
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

// CI's Linux renders in software (SwiftShader); CAD_TEST_SWIFTSHADER=1 does so on a Mac too, and
// VIEWER_E2E_CPU_THROTTLE=N slows each page's CPU N times (CDP), to reproduce a slow runner locally.
const angle = process.platform === "darwin" && process.env.CAD_TEST_SWIFTSHADER !== "1" ? "metal" : "swiftshader";
const cpuThrottle = Number(process.env.VIEWER_E2E_CPU_THROTTLE || 0);
// VIEWER_E2E_PREVIEW_FRAME_MS=N draws a frame of N ms every frame while Preview is up, as a software
// GPU accumulating Render's samples on a slow runner does (CI's camera gate once took 46 s to settle there).
const previewFrameMs = Number(process.env.VIEWER_E2E_PREVIEW_FRAME_MS || 0);
const browserFlags = [`--use-angle=${angle}`, "--ignore-gpu-blocklist"];
if (angle === "swiftshader") browserFlags.push("--enable-unsafe-swiftshader");
console.log(`viewer browser e2e: Chromium ANGLE=${angle}${cpuThrottle > 1 ? `, CPU throttled ${cpuThrottle}x` : ""}`);
const browser = await chromium.launch({
  headless: true,
  args: browserFlags,
});

async function newPage() {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, extraHTTPHeaders: process.env.VIEWER_TEST_TOKEN ? { Authorization: `Bearer ${process.env.VIEWER_TEST_TOKEN}` } : {} });
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
    // A file is named by its absolute path in every request: the page addresses documents by id
    // (`/<id>`) and asks for a file by the path its row gives.
    if (parsed.pathname === "/__cad/catalog") {
      const file = parsed.searchParams.get("file") || "";
      if (file && !/^(?:\/|[a-z]:\/)/i.test(file)) {
        errors.push(`a relative file reached ${parsed.pathname}: ${file}`);
      }
    }
    // The page reads its own origin alone: a document the cadgen engine serves is read through
    // the viewer (`/__cad/api/...`), never from the engine's own port.
    if (["http:", "https:"].includes(parsed.protocol) && parsed.origin !== viewerOrigin) {
      errors.push(`a request to another origin: ${request.method()} ${url} (${request.resourceType()})`);
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const page = await context.newPage();
  if (cpuThrottle > 1) await (await context.newCDPSession(page)).send("Emulation.setCPUThrottlingRate", { rate: cpuThrottle });
  if (previewFrameMs > 0) {
    await page.addInitScript((ms) => {
      // A frame every frame while Preview is up, each one ms long: Render accumulating its samples
      // in software, which on a slow runner is drawing for tens of seconds after the camera stops.
      const draw = () => {
        if (document.querySelector("[data-preview-view]")) {
          const end = performance.now() + ms;
          while (performance.now() < end) { /* the frame's draw */ }
        }
        requestAnimationFrame(draw);
      };
      requestAnimationFrame(draw);
    }, previewFrameMs);
  }
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
            canvases: [...document.querySelectorAll('canvas')].map(canvas => canvas.getBoundingClientRect().toJSON()),
            camera: window.__cadCamera?.(),
            load: window.__cadViewerLoad,
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
  // A page names its document by id, `/<id>`: the file's, which the server derives from its canonical
  // path and registers when the catalog is asked for it (as Select File and the home do).
  const base = args.url.replace(/\/$/, "");
  // These one-off Node requests can be separated by more than the server's idle timeout.
  // Close them from first use so its connection pool cannot race an idle socket closing.
  const catalog = await page.request.get(`${base}/__cad/catalog?file=${encodeURIComponent(path.join(root, file))}`, {
    headers: { Connection: "close" },
  });
  const id = (await catalog.json()).entries?.[0]?.id;
  if (!id) fail(`the catalog gave ${file} no document id`);
  await page.goto(`${base}/${id}`, {
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
  // drawing has none, and its viewport's `aria-busy` is the whole of it. Then a frame is painted.
  if (!/\.dxf$/i.test(file)) {
    await page.waitForFunction(() => {
      const bounds = window.__cadModelBounds?.();
      return Array.isArray(bounds?.min) && Array.isArray(bounds?.max)
        && bounds.min.some((value, axis) => Number(bounds.max[axis]) - Number(value) > 0);
    }, null, { timeout: 120_000 });
  }
  await painted(page);
  return canvas;
}

/** Once the page has painted a frame after this: the second animation frame from now runs after the first one's paint. */
function painted(page) {
  return page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
}

/** The staged model's bounds, from the stage its renderer publishes (`__cadStage`). */
const MODEL_BOUNDS_SCRIPT = () => {
  window.__cadModelBounds = () => {
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
  await painted(page);  // a menu the press opened is drawn by then
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
        buttons.filter((button) => !button.closest("[data-view-controls]")).map((button) => button.getAttribute("aria-label")));
      for (const label of fixture.tools) if (!strip.includes(label)) failures.push(`${fixture.format}: missing ${label} (strip: ${strip.join(", ")})`);
      if (!fixture.tools.length && strip.length) failures.push(`${fixture.format}: tools on a file that has none (${strip.join(", ")})`);
      if (!fixture.tools.includes("Measure") && strip.includes("Measure")) {
        failures.push(`${fixture.format}: Measure is offered on a view that cannot measure (must be hidden, not disabled)`);
      }
      // What there is to read of the file is the file sidebar's, a tile per section, never a tool.
      const tiles = await page.locator("[data-file-sidebar-tools] button").evaluateAll((buttons) =>
        buttons.map((button) => button.getAttribute("aria-label")));
      for (const label of fixture.sections) if (!tiles.includes(label)) failures.push(`${fixture.format}: missing the ${label} tile (sidebar: ${tiles.join(", ")})`);
      if (!fixture.sections.length && tiles.length) failures.push(`${fixture.format}: a file sidebar on a file with nothing to read (${tiles.join(", ")})`);
      // Projection, Display and Preview end the tool strip on 3D views; drawings have none.
      const controls = await page.locator("[data-cad-toolbar] [data-view-controls] button").evaluateAll((buttons) =>
        buttons.map((button) => button.getAttribute("aria-label")));
      const expected = fixture.threeD ? ["Projection: Orthographic", "Display mode: Solid", "Preview"] : [];
      if (JSON.stringify(controls) !== JSON.stringify(expected)) failures.push(`${fixture.format}: the view's controls are ${JSON.stringify(controls)}`);
      if (await page.locator("[data-viewer-navbar] [data-view-controls] button").count()) failures.push(`${fixture.format}: editor view controls in the navbar`);
      const menus = await page.getByRole("button", { name: "Menu", exact: true }).count();
      if (menus !== 1) failures.push(`${fixture.format}: ${menus} app menus (one on every file)`);
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

// Inspect is the tools view, in the file's mode (Solid); Render is Preview's alone, in by
// Preview at the strip's end and out by Exit preview in Preview's bar, each once the cover over the crossing has lifted.
async function selectViewingMode(page, current, next) {
  const [press, arrive] = next === "Render" ? ["Preview", "Exit preview"] : ["Exit preview", "Preview"];
  if (!(await page.getByRole("button", { name: press, exact: true }).count())) fail(`viewing mode: expected ${current} before switching to ${next}`);
  const button = page.getByRole("button", { name: press, exact: true });
  if (next !== "Render") {
    // Preview's bar hides two seconds after the pointer last rests over the view (counted from the frame
    // that shows it), and a person's pointer, moving to Exit preview, brings it back and holds it while it
    // rests there: this pointer does the same. Playwright checks what is under a point before it moves
    // there, so a press alone on a hidden bar would never bring it back.
    const visible = () => page.locator('[data-preview-bar][data-state="visible"]').waitFor({ state: "attached" });
    const view = await page.locator("[data-preview-view]").first().boundingBox();
    await page.mouse.move(view.x + view.width / 2, view.y + view.height / 2);
    await visible();
    const box = await button.boundingBox();
    const [x, y] = [box.x + box.width / 2, box.y + box.height / 2];
    await page.mouse.move(x, y);
    await visible();
    await page.mouse.move(x + 1, y);  // over the bar while it shows: resting there holds it
    await visible();
  }
  await button.click();
  await page.getByRole("button", { name: arrive, exact: true }).waitFor();
  await page.waitForFunction(() => !document.querySelector("[data-preview-cover]"));
}

// --- camera grounding -----------------------------------------------------
// The camera is fitted ONCE per model, to its zero pose: a mode round trip does
// not move it, a saved REVISION (a new zero pose) does not move it either, and the
// explicit Reset view re-fits to the zero pose there is now. The tolerance is only there for
// the last-bit drift OrbitControls' own update leaves behind (observed at ~1e-15
// relative); the regression this catches moved the framing by 2.4% and the pivot
// by a quarter of the model.
// Relative. A mode switch rebuilds the camera through floating-point conversions that land a
// few 1e-9 off on some runs; 1e-6 is still far below any move a person could see.
const CAMERA_EPSILON = 1e-6;

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
  // Reset changes framing on the presented model: presentation and a camera at
  // rest are what it waits for.
  await settledCameraFrame(page, { stage: "reset view" });
}

// --- the camera across modes ----------------------------------------------
// Inspect (the tools view, Solid) and Render (Preview) look at one model: Preview converts
// the camera to its perspective, keeping what it looks at, and leaving it gives the tools view's
// camera back exactly. A model opens framed against its own zero pose.
async function settledCameraFrame(page, { projection = null, stage, timeout = 60_000 } = {}) {
  const startedAt = Date.now();
  cameraReadiness.set(page, { ...cameraReadiness.get(page), pending: { stage, projection } });
  // Projection is published during scene reconciliation, before Render's
  // environment and first frame are necessarily ready. The presentation host
  // clears aria-busy only after drawing that destination scene. The whole model
  // must be loaded, and the camera at rest by the controller's own account
  // (`settling`: no gesture, transition, held key or damping still moves it),
  // for every framing assertion. The frame the poll runs in was drawn at rest.
  // And the camera is framed for the box the canvas has on screen: leaving Preview brings the
  // navbar back a commit after the tools view returns, and the viewport answers that resize (its
  // refit of the orthographic half-height) in its ResizeObserver, which runs after this frame's
  // animation callbacks -- so a poll can see the new box with the camera still framed for Preview's
  // taller one. Its projection's aspect is the viewport's once the resize is handled.
  const ready = await page.waitForFunction(({ want }) => {
    const canvas = document.querySelector("canvas");
    const camera = window.__cadCamera?.();
    const box = canvas ? canvas.clientWidth / canvas.clientHeight : NaN;
    if (!canvas || !camera || camera.settling !== false || (want && camera.projection !== want)
      || !(Math.abs(Number(camera.aspect) - box) <= 1e-6 * box)
      || canvas.closest("[aria-busy]")?.getAttribute("aria-busy") !== "false"
      || getComputedStyle(canvas).visibility !== "visible"
      || document.querySelector("[data-viewer-transition]")
      || !window.__cadViewerLoad?.complete) return false;
    // A view draws through the page's GPU device and is handed its frames as bitmaps; a browser
    // without one draws in a context of the canvas's own.
    const gl = canvas.getContext("webgl2");
    if (gl) {
      if (gl.isContextLost()) throw new Error('camera: presented canvas has lost its WebGL2 context');
      gl.finish();
    } else if (!(window.__cadGpuDevice?.().views > 0)) throw new Error('camera: presented canvas draws through no GPU device');
    return { camera, width: canvas.width, height: canvas.height };
  }, { want: projection }, { timeout, polling: "raf" });
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

    // Preview converts the camera to its projection, keeping what it looks at, and leaving it
    // is exact.
    await switchMode(page, "Inspect", "Render");
    const renderFit = await cameraState(page);
    if (!renderFit) failures.push("mode camera: the camera seam published nothing in Render");
    else if (renderFit.target.some((value, axis) => Math.abs(value - inspectFit.target[axis]) > 1e-6)) {
      failures.push(`mode camera: Render re-aimed the view — ${describeCamera(renderFit)}`);
    }

    await switchMode(page, "Render", "Inspect");
    await cameraHeld(page, inspectFit, "returning to Inspect");

    // A view taken by hand survives a visit to Preview, and what is done to the camera in
    // Preview is Preview's: the tools view gets its own back.
    await orbitAndZoom(page);
    const handFramed = await cameraMoved(page, inspectFit, "orbit and zoom in Inspect");
    if (handFramed) {
      await switchMode(page, "Inspect", "Render");
      await switchMode(page, "Render", "Inspect");
      await cameraHeld(page, handFramed, "Inspect after a round trip through Render");
      await switchMode(page, "Inspect", "Render");
      await orbitAndZoom(page);
      await cameraMoved(page, renderFit, "orbit and zoom in Render");
      await switchMode(page, "Render", "Inspect");
      await cameraHeld(page, handFramed, "Inspect after the camera moved in Render");
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
    console.log("  mode camera: Preview converts the view without re-aiming it, leaving it returns "
      + "the tools view's camera, and a new model is framed against its own box");
  } finally {
    await context.close();
  }

  // A REVISION follows the camera's owner (`kit/camera/cameraTouch.js`). While the camera is still
  // the opening fit, nobody's yet, a rebuild whose box changed is fitted again, as the open
  // fitted it: the grown arm (x = 158 where the first revision stopped at 58) comes up framed
  // whole, at 100% of its own ruler, looking the way it did. Once the person has taken the camera,
  // a rebuild keeps it exactly, its pose and its zoom, even as the model shrinks back; their own
  // fit hands it back and frames the revision on screen. A fresh tab, so the camera at the start
  // is the open-time fit and not one the tab kept for this file.
  const revision = await newPage();
  const rebuilt = async (from, reaches) => {
    fs.copyFileSync(path.join(root, ".revision", from), path.join(root, "hinge.step"));
    const landed = await revision.page.waitForFunction((grown) => {
      const x = Number(window.__cadModelBounds?.()?.max?.[0]);
      return grown ? x > 100 : x > 0 && x < 100;
    }, reaches === "grown", { timeout: 60_000 }).then(() => true).catch(() => false);
    if (!landed) failures.push(`step revision: the viewer never picked up the ${reaches} model`);
    else await settledCameraFrame(revision.page, { stage: `hinge ${reaches}` });
    return landed;
  };
  const sameDirection = (a, b) => {
    const unit = camera => { const d = camera.position.map((v, i) => v - camera.target[i]); const l = Math.hypot(...d) || 1; return d.map(v => v / l); };
    return unit(a).every((value, axis) => Math.abs(value - unit(b)[axis]) <= 1e-6);
  };
  try {
    await openFile(revision.page, "hinge.step");
    await settledCameraFrame(revision.page, { stage: "hinge before its revision" });
    const firstFit = await cameraState(revision.page);
    if (firstFit?.untouched !== true) failures.push(`step revision: the opening fit does not read as untouched (${firstFit?.untouched})`);
    if (await rebuilt("hinge.step", "grown")) {
      const refit = await cameraState(revision.page);
      if (!(Number(refit?.halfHeight) > Number(firstFit?.halfHeight))) {
        failures.push(`step revision: an untouched camera was not fitted to the grown model — ${describeCamera(refit)}, `
          + `was ${describeCamera(firstFit)}`);
      } else if (Math.abs(Number(refit?.zoomPercent) - 100) > 0.5) {
        failures.push(`step revision: the untouched re-fit does not read as 100% (${refit?.zoomPercent})`);
      } else if (!sameDirection(refit, firstFit)) {
        failures.push(`step revision: the untouched re-fit turned the view — ${describeCamera(refit)}`);
      }

      // The person takes the camera: a rebuild now keeps it, though the model shrank back.
      await orbitAndZoom(revision.page);
      const handFramed = await cameraMoved(revision.page, refit, "orbit and zoom on the grown hinge");
      if (handFramed?.untouched !== false) failures.push(`step revision: an orbit did not touch the camera (${handFramed?.untouched})`);
      if (handFramed && await rebuilt("hinge-first.step", "first")) {
        // The zoom ruler is measured against the zero pose, which the revision changed: the pose
        // is compared without it.
        const kept = await cameraState(revision.page);
        const drift = cameraDrift(kept && { ...kept, zoomPercent: handFramed.zoomPercent }, handFramed);
        if (!(drift <= CAMERA_EPSILON)) {
          failures.push(`step revision: a touched camera moved on a rebuild (${drift.toExponential(2)} relative) — `
            + `${describeCamera(kept)}, was ${describeCamera(handFramed)}`);
        }
        // Their fit, F, frames the revision on screen, about its own centre, at the angle they
        // left (the ruler's 100% is the default angle's, so it is not read here), and the camera
        // is untouched again.
        await revision.page.keyboard.press("f");
        await settledCameraFrame(revision.page, { stage: "the fit F makes" });
        const fitted = await cameraState(revision.page);
        if (!fitted || fitted.target.some((value, axis) => Math.abs(value - firstFit.target[axis]) > 1e-6) || fitted.zoom !== 1) {
          failures.push(`step revision: F did not frame the first revision — ${describeCamera(fitted)}`);
        } else if (!sameDirection(fitted, handFramed)) {
          failures.push(`step revision: F turned the view — ${describeCamera(fitted)}`);
        }
        if (fitted?.untouched !== true) failures.push(`step revision: a fit did not hand the camera back (${fitted?.untouched})`);
      }
    }
    if (revision.errors.length) failures.push(`step revision: ${revision.errors.join(" | ")}`);
    console.log("  step revision: an untouched camera fits a rebuilt box, a touched one is kept, and a fit hands it back");
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

