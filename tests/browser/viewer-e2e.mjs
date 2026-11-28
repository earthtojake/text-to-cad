#!/usr/bin/env node
// Real-browser coverage for the bundled Viewer: every load path opens through the
// real backend and bundle, the camera holds across modes, and a saved revision re-fits a
// camera nobody has touched and keeps one the person took; and a model `cad share` shared opens, with no
// engine running, from the share service itself, run locally, under its content security policy: on
// screen, a face's facts from its table, read-only parameters, nothing asked of an engine. CI runs all of it;
// there is no local-only set. Fixture and process lifecycle belong to
// scripts/test/test-viewer-browser.sh.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const { chromium } = createRequire(path.join(REPO, "packages/core/package.json"))("playwright");
const { PNG } = createRequire(path.join(REPO, "apps/web/package.json"))("pngjs");

function parseArgs(argv) {
  const args = { url: "", dir: "", out: "", only: "", share: "", shareAgain: "", shareBoard: "", shareSchematic: "", plate: "", prompt: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === "--url") args.url = argv[++i] || "";
    else if (flag === "--dir") args.dir = argv[++i] || "";
    // What `cad share` printed, sharing the model and then sharing it again unchanged.
    else if (flag === "--share") args.share = argv[++i] || "";
    else if (flag === "--share-again") args.shareAgain = argv[++i] || "";
    else if (flag === "--share-board") args.shareBoard = argv[++i] || "";
    else if (flag === "--share-schematic") args.shareSchematic = argv[++i] || "";
    // The share fixture's model, by its document id, for the prompt gate on the engine's page; and the file the
    // prompt gate writes the prompt it copied to, for the share gate to compare the shared page's with.
    else if (flag === "--plate") args.plate = argv[++i] || "";
    else if (flag === "--prompt") args.prompt = argv[++i] || "";
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
  // `tools` is the file's own tool strip; unavailable tools are hidden. A `threeD` view has Preview beside the
  // navbar's Display button, and Projection in Display's card; `sections` are the view's panel's tabs it must
  // have (what there is to read of the file, whatever the tool: a mesh's bodies, a drawing's layers).
  { format: "stl", file: "smoke.stl", parts: false, tools: ["Select", "Draw", "Clip"], sections: ["Model"], threeD: true },
  // A STEP: read by the engine, drawn as an engine document is.
  { format: "step", file: "assembly.step", parts: true, tools: ["Select", "Draw", "Measure", "Clip"], sections: ["Model"], threeD: true },
  // A drawing is line work, not shaded surfaces: its outline covers a fraction of what a solid does.
  { format: "dxf", file: "smoke.dxf", parts: false, tools: ["Select", "Draw", "Measure"], sections: ["Layers"], threeD: false, minCoverage: 0.003 },
  { format: "urdf", file: "smoke.urdf", parts: false, tools: ["Select", "Draw", "Measure", "Clip"], sections: ["Links"], threeD: true },
  // A cadgen engine document: served by the engine, read by the page from it, and picked,
  // measured and laid out as a STEP's is, with a STEP's pick menus on Select's and Measure's chevrons.
  { format: "xbf", file: "smoke.xbf", parts: true,
    tools: ["Select", "Filter: everything", "Draw", "Measure", "Measure filter: everything", "Clip"], sections: ["Model"], threeD: true },
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

// The engine's page's gates read its server (`--url`) and the project it serves (`--dir`); the share gate what
// `cad share` printed (`--share`), its links on the share service.
if (!args.url && !args.share) fail("--url or --share is required; use the self-contained scripts/test runner");
if (args.url) {
  if (!args.dir || !path.isAbsolute(args.dir)) fail("--dir must name the absolute served test project");
  for (const fixture of fixtures) {
    if (!fs.existsSync(path.join(root, fixture.file))) fail(`missing test input ${fixture.file}`);
  }
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
    if (parsed.pathname === "/api/v1/documents" && parsed.searchParams.has("path")) {
      const file = parsed.searchParams.get("path") || "";
      if (file && !/^(?:\/|[a-z]:\/)/i.test(file)) {
        errors.push(`a relative file reached ${parsed.pathname}: ${file}`);
      }
    }
    // The page reads its own origin alone: a document the cadgen engine serves is read through
    // the page's own origin (`/api/v1/...`), never from the engine's own port.
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
    if (response.status() < 400 || !response.url().startsWith(`${viewerOrigin}/api/`)) return;
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
  // path and registers when its envelope is asked for by that path (as Select File and the home do).
  const base = args.url.replace(/\/$/, "");
  // These one-off Node requests can be separated by more than the server's idle timeout.
  // Close them from first use so its connection pool cannot race an idle socket closing.
  const catalog = await page.request.get(`${base}/api/v1/documents?path=${encodeURIComponent(path.join(root, file))}`, {
    headers: { Connection: "close" },
  });
  const id = (await catalog.json()).documents?.[0]?.id;
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
      // The test's device is a new person's: no dialog over the file (What's new is an updated device's).
      const dialogs = await page.getByRole("dialog").allInnerTexts();
      if (dialogs.length) failures.push(`${fixture.format}: a dialog over a new device's file: ${dialogs[0].split("\n")[0]}`);
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
      if (!fixture.tools.length && strip.length) failures.push(`${fixture.format}: tools on a file that has none (${strip.join(", ")})`);
      if (!fixture.tools.includes("Measure") && strip.includes("Measure")) {
        failures.push(`${fixture.format}: Measure is offered on a view that cannot measure (must be hidden, not disabled)`);
      }
      // What there is to read of the file is the view's panel's, a tab per section (a panel of one has no
      // row of tabs: each section is labelled by its name), never a tool.
      const tabs = await page.locator("[data-flat-panel] [data-flat-panel-section]").evaluateAll((sections) =>
        sections.map((section) => section.getAttribute("aria-label")));
      for (const label of fixture.sections) if (!tabs.includes(label)) failures.push(`${fixture.format}: missing the ${label} tab (panel: ${tabs.join(", ")})`);
      if (!fixture.sections.length && tabs.length) failures.push(`${fixture.format}: a panel on a file with nothing to read (${tabs.join(", ")})`);
      // How the view is drawn is the navbar's, never the tool strip's: every file's Display button (its card holds
      // Projection on a 3D view), and Preview beside it on a 3D view alone.
      if (await page.locator("[data-cad-toolbar] :is([data-display-settings], [data-view-preview])").count()) failures.push(`${fixture.format}: view controls on the tool strip`);
      const display = page.locator("[data-viewer-navbar] button[data-display-settings]");
      if (await display.count() !== 1) failures.push(`${fixture.format}: ${await display.count()} Display buttons in the navbar (one on every file)`);
      else if ((await display.getAttribute("data-view-projection") !== null) !== fixture.threeD) {
        failures.push(`${fixture.format}: Display's card ${fixture.threeD ? "has no" : "has a"} Projection`);
      }
      const preview = await page.locator("[data-viewer-navbar] button[data-view-preview]").count();
      if (preview !== (fixture.threeD ? 1 : 0)) failures.push(`${fixture.format}: ${preview} Preview buttons in the navbar`);
      // The logo is the way home, a link to it, on every file; the links and Settings are the panel's foot's.
      const logos = await page.locator("[data-viewer-navbar]").getByRole("link", { name: "Home", exact: true }).count();
      if (logos !== 1) failures.push(`${fixture.format}: ${logos} logos linking home (one on every file)`);
      const menu = await canvasMenuItems(page, canvas);
      // Every view has the menu, its framing always (`kit/shell/viewMenu.js`); a file of parts, its tree's entries too.
      for (const item of framing) if (!menu.includes(item)) failures.push(`${fixture.format}: menu missing ${item}`);
      if (fixture.parts) {
        for (const item of presentTree) if (!menu.includes(item)) failures.push(`${fixture.format}: parts menu missing ${item}`);
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
// the navbar's Preview and out by Exit preview in Preview's bar, each once the cover over the crossing has lifted.
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

// A 3D fit frames the model in the room under the view's tool strip and centres it there
// (`kit/camera/viewportCameraFit.js`, `fitRoom`): the camera's target stands above the point the
// fit aims at, along the view's screen up, by the share of the half height the strip takes. What
// the tools view aims at is that point; Preview's view has no strip and aims at it directly.
// `reach` is the strip's (`stripReach`) when the camera was read; an orthographic camera at 1x.
async function stripReach(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector("canvas");
    const frame = canvas?.closest("[data-slot=cad-file-view]");
    if (!canvas || !frame || canvas.closest("[data-preview-view]")) return { clear: 0, height: 1 };
    const clear = Number.parseFloat(getComputedStyle(frame).getPropertyValue("--cad-tools-bottom"));
    return { clear: Number.isFinite(clear) && clear > 0 ? clear : 0, height: Math.max(1, canvas.clientHeight) };
  });
}

function aimPoint(camera, reach) {
  if (!camera || camera.projection !== "orthographic" || !(reach?.clear > 0)) return camera?.target;
  const share = Math.max(1 - reach.clear / reach.height, 0.5);
  const offset = camera.position.map((value, axis) => value - camera.target[axis]);
  const length = Math.hypot(...offset) || 1;
  const direction = offset.map((value) => value / length);
  const along = camera.up.reduce((sum, value, axis) => sum + value * direction[axis], 0);
  const upright = camera.up.map((value, axis) => value - along * direction[axis]);
  const upLength = Math.hypot(...upright) || 1;
  const lift = (1 - share) * Number(camera.halfHeight) / (Number(camera.zoom) || 1);
  return camera.target.map((value, axis) => value - lift * upright[axis] / upLength);
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
    const inspectAim = aimPoint(inspectFit, await stripReach(page));
    if (inspectFit?.projection !== "orthographic") {
      failures.push(`mode camera: Inspect did not open orthographic (${inspectFit?.projection})`);
    }

    // Preview converts the camera to its projection, keeping what it looks at (the point the tools
    // view's fit centres under its strip; Preview has none), and leaving it is exact.
    await switchMode(page, "Inspect", "Render");
    const renderFit = await cameraState(page);
    if (!renderFit) failures.push("mode camera: the camera seam published nothing in Render");
    else if (renderFit.target.some((value, axis) => Math.abs(value - inspectAim[axis]) > 1e-6)) {
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
    const firstAim = aimPoint(firstFit, await stripReach(revision.page));
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
        // is untouched again. Each fit aims at the box's centre (`aimPoint`: its target stands above
        // it along that angle's screen up, under the strip).
        await revision.page.keyboard.press("f");
        await settledCameraFrame(revision.page, { stage: "the fit F makes" });
        const fitted = await cameraState(revision.page);
        const fittedAim = fitted && aimPoint(fitted, await stripReach(revision.page));
        if (!fitted || fittedAim.some((value, axis) => Math.abs(value - firstAim[axis]) > 1e-6) || fitted.zoom !== 1) {
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

// Every content security policy violation the page meets, as it reports them, for the gate to say.
const CSP_VIOLATIONS_SCRIPT = () => {
  window.__cspViolations = [];
  document.addEventListener("securitypolicyviolation", event => window.__cspViolations.push({
    directive: event.effectiveDirective, blocked: event.blockedURI, source: event.sourceFile, line: event.lineNumber, sample: event.sample }));
};

// What the page copies, kept where the gate can read it: the clipboard's text, however it is written (a pending
// prompt goes as a clipboard item whose text is still on its way).
const CLIPBOARD_SCRIPT = () => {
  window.__copied = [];
  const keep = (text) => { window.__copied.push(String(text)); };
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: {
    writeText: async (text) => keep(text),
    write: async (items) => {
      for (const item of items) for (const type of item.types) if (type === "text/plain") keep(await (await item.getType(type)).text());
    },
    readText: async () => window.__copied.at(-1) ?? "",
    read: async () => [],
  } });
};

// A copied prompt as its parts: its lines but the snapshot's JSON block, and that packet (null without one).
function promptParts(message) {
  const block = /```json\n([\s\S]*?)\n```/.exec(message);
  return { text: block ? message.replace(block[0], "<packet>") : message, packet: block ? JSON.parse(block[1]) : null };
}
// A packet with each view's framing left out (its camera, and its picture's size): what the page's layout decides.
function framed(packet) {
  if (!packet) return packet;
  return { ...packet, jobs: (packet.jobs || []).map(({ camera, outputs, ...job }) => ({ ...job,
    outputs: (outputs || []).map(({ width, height, ...output }) => output) })) };
}

// The engine's page: a Quick Edit on the share fixture's model, copied, names the model by its document id and
// carries its snapshot inline (no file, no path), and is kept for the share gate to compare.
async function promptGate() {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, extraHTTPHeaders: process.env.VIEWER_TEST_TOKEN ? { Authorization: `Bearer ${process.env.VIEWER_TEST_TOKEN}` } : {} });
  try {
    const page = await context.newPage();
    page.setDefaultTimeout(60_000);
    await page.addInitScript(CLIPBOARD_SCRIPT);
    await page.goto(`${args.url.replace(/\/$/, "")}/${args.plate}`, { waitUntil: "domcontentloaded" });
    await page.locator('[data-slot="cad-file-view"] [aria-busy="false"]').first().waitFor({ timeout: 120_000 });
    await page.locator("[data-quick-edit-note]").click();
    await page.keyboard.type("Make the plate thicker.");
    await page.locator('[data-quick-edit-action="copy"]').click();
    await page.waitForFunction(() => window.__copied.length > 0, null, { timeout: 30_000 });
    const prompt = await page.evaluate(() => window.__copied.at(-1));
    const said = promptParts(prompt);
    const outputs = (said.packet?.jobs || []).flatMap(job => job.outputs || []);
    if (!prompt.startsWith("Make the plate thicker.") || !prompt.includes(`File: ${args.plate}`) || said.packet?.input !== args.plate
      || !outputs.length || outputs.some(output => "path" in output) || /\.snapshot\.json/.test(prompt)) {
      failures.push(`prompt: the copied prompt does not carry its snapshot inline: ${JSON.stringify(prompt)}`);
    }
    if (args.prompt) fs.writeFileSync(args.prompt, prompt);
    // The engine's page offers no Download files: the files are the person's own.
    await page.getByTestId("file-actions").click();
    await page.getByRole("menu").waitFor();
    if (await page.locator("[data-share-files]").count()) failures.push("prompt: Download files in the engine page's file menu");
    await page.keyboard.press("Escape");
  } finally {
    await context.close();
  }
}

async function shareGate() {
  // A model shared as a person's agent shares one: `cad share --yes` (the runner's), against this checkout's
  // share service run locally (`apps/share/serve.mjs`, the Worker itself over Node's http), which also serves
  // the bundled client; then shared again, unchanged. The gate is handed what the command printed each time
  // (`--share`, `--share-again`, its JSON): the two links, and what travelled.
  const shared = JSON.parse(fs.readFileSync(args.share, "utf8"));
  if (shared.ok !== true || typeof shared.view !== "string" || typeof shared.delete !== "string") {
    fail(`--share names no share the command made: ${args.share}`);
  }
  const viewLink = new URL(shared.view);
  const origin = viewLink.origin;
  const id = viewLink.pathname.slice(1);
  const secret = new URLSearchParams(new URL(shared.delete).hash.slice(1)).get("delete") || "";
  // The view link is the share's address alone: its id opens it, and nothing follows it.
  if (!/^[A-Za-z0-9_-]{22}$/.test(id) || viewLink.search || viewLink.hash) fail("the view link is not a share's address alone");
  if (!secret || new URL(shared.delete).pathname.slice(1) !== id) fail("the share's delete link carries no secret, or names another share");
  // The files that made it are a zip beside the view, on the same id (the runner imports it, byte for byte).
  if (shared.zip !== `${origin}/${id}.zip`) failures.push(`share: the files' link is ${JSON.stringify(shared.zip)}`);
  // Shared again with nothing changed: the same links, and no file travelled again.
  if (args.shareAgain) {
    const again = JSON.parse(fs.readFileSync(args.shareAgain, "utf8"));
    if (again.ok !== true || again.view !== shared.view || again.delete !== shared.delete) failures.push("share: sharing again did not keep the links");
    if (!(shared.sent?.files > 0) || shared.sent.files !== shared.stored?.files) {
      failures.push(`share: the first share sent ${JSON.stringify(shared.sent)} of ${JSON.stringify(shared.stored)}`);
    }
    if (again.sent?.files !== 0 || again.sent?.packs !== 0 || again.stored?.files !== shared.stored?.files) {
      failures.push(`share: sharing the unchanged model again sent ${JSON.stringify(again.sent)} of ${JSON.stringify(again.stored)}`);
    }
  }
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  // The packs the page fetched: each is named by its content, so the browser may keep it as it is.
  const packs = [];
  context.on("response", (response) => {
    if (/^\/v1\/shares\/[^/]+\/packs\//.test(new URL(response.url()).pathname)) {
      packs.push({ status: response.status(), cache: response.headers()["cache-control"] || "" });
    }
  });
  const errors = [];
  const asked = [];
  await context.route("**/*", async (route) => {
    const request = route.request();
    asked.push({ url: request.url(), method: request.method(), headers: await request.allHeaders(), body: request.postData() || "" });
    if (new URL(request.url()).origin !== origin) {
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  });
  const logged = [];
  // A page that says a share is gone answered 404: the browser's own line for it is no error of the page's.
  async function open(address, { gone = false } = {}) {
    const page = await context.newPage();
    page.setDefaultTimeout(60_000);
    page.on("pageerror", (error) => errors.push(`page: ${error.message || error}`));
    page.on("console", (message) => {
      logged.push(message.text());
      if (message.type() === "error" && !(gone && /status of 404/.test(message.text()))) errors.push(`console: ${message.text()}`);
    });
    await page.addInitScript(MODEL_BOUNDS_SCRIPT);
    await page.addInitScript(CSP_VIOLATIONS_SCRIPT);
    await page.addInitScript(CLIPBOARD_SCRIPT);
    const answer = await page.goto(`${origin}${address}`, { waitUntil: "domcontentloaded" });
    page.historyAtOpen = await page.evaluate(() => history.length);
    page.policy = answer?.headers()["content-security-policy"] || "";
    return page;
  }
  const violations = [];
  async function close(page, what) {
    for (const violation of await page.evaluate(() => window.__cspViolations)) violations.push({ what, ...violation });
    if (diagnosticDir) {
      fs.mkdirSync(diagnosticDir, { recursive: true });
      await page.screenshot({ path: path.join(diagnosticDir, `diagnostic-share-${what}.png`), timeout: 3000 }).catch(() => {});
    }
    await page.close();
  }
  try {
    // The view: the model on screen, titled by its document's name.
    const view = await open(`/${id}`);
    await view.locator('[data-slot="cad-file-view"] [aria-busy="false"]').first().waitFor({ timeout: 120_000 });
    await view.waitForFunction(() => {
      const bounds = window.__cadModelBounds?.();
      return Array.isArray(bounds?.min) && bounds.min.some((value, axis) => Number(bounds.max[axis]) - Number(value) > 0);
    }, null, { timeout: 120_000 });
    await painted(view);
    const drawn = coverage(PNG.sync.read(await view.locator("canvas").first().screenshot()));
    if (drawn < 0.03) failures.push(`share: no foreground model region (${drawn.toFixed(4)})`);
    results.push({ format: "share", coverage: drawn });
    if (await view.title() !== shared.document.name) failures.push(`share: the page is titled ${JSON.stringify(await view.title())}, not its document's name`);
    // The service's policy holds the page to its own origin, and allows its inline scripts by their hashes alone.
    const scripts = /(?:^|;\s*)script-src ([^;]*)/.exec(view.policy)?.[1] || "";
    if (!/(?:^|;\s*)connect-src 'self'/.test(view.policy) || /'unsafe-inline'/.test(scripts)) {
      failures.push(`share: the page's content security policy is not the service's: ${JSON.stringify(view.policy)}`);
    }
    // Its ⋯ holds one item, Download files: the share's zip of the files that made it, which the service sends as an
    // attachment, so the browser saves it and the page stays where it is.
    await view.getByTestId("file-actions").click();
    const download = view.locator("[data-share-files]");
    await download.waitFor({ timeout: 30_000 });
    const items = await view.getByRole("menuitem").allTextContents();
    if (await download.getAttribute("href") !== `${origin}/${id}.zip` || items.length !== 1 || items[0] !== "Download files") {
      failures.push(`share: the file menu is ${JSON.stringify(items)}, not Download files of the share's zip`);
    }
    const [saved] = await Promise.all([view.waitForEvent("download", { timeout: 30_000 }), download.click()]);
    const zipped = fs.readFileSync(await saved.path());
    if (zipped.subarray(0, 2).toString("latin1") !== "PK" || !saved.suggestedFilename().endsWith(".zip") || view.url() !== `${origin}/${id}`) {
      failures.push(`share: Download files saved ${JSON.stringify(saved.suggestedFilename())} and left the page at ${view.url().replaceAll(id, "<id>")}`);
    }
    // A prompt copied from the shared view names the share's link, never this computer's model, and tells the
    // agent how to get the files that made it.
    await view.locator("[data-quick-edit-note]").click();
    await view.keyboard.type("Make the plate thicker.");
    await view.locator('[data-quick-edit-action="copy"]').click();
    await view.waitForFunction(() => window.__copied.length > 0, null, { timeout: 30_000 });
    const prompt = await view.evaluate(() => window.__copied.at(-1));
    const link = `${origin}/${id}`;
    const said = promptParts(prompt);
    if (!prompt.startsWith("Make the plate thicker.") || !prompt.includes(`File: ${link}`) || prompt.includes(shared.document.id)
      || said.packet?.input !== link) {
      failures.push(`share: the copied prompt does not name the share as its file: ${JSON.stringify(prompt.replaceAll(id, "<id>"))}`);
    }
    // What the engine's page copied for the same model (the prompt gate's), with this page's address for its own:
    // the same lines and the same packet, but for each view's framing, which each page's layout makes.
    if (args.prompt && fs.existsSync(args.prompt)) {
      const local = promptParts(fs.readFileSync(args.prompt, "utf8").replaceAll(shared.document.id, link));
      if (local.text !== said.text || JSON.stringify(framed(local.packet)) !== JSON.stringify(framed(said.packet))) {
        failures.push(`share: the shared page's prompt is not the engine page's with the share's address: ${JSON.stringify({ local: local.text, shared: said.text })}`);
      }
    }
    // The id stays where the address holds it: in no storage, and in no other history entry.
    const kept = await view.evaluate(() => ({ history: history.length, href: location.href,
      storage: JSON.stringify({ ...sessionStorage }) + JSON.stringify({ ...localStorage }) }));
    if (kept.history !== view.historyAtOpen || kept.href !== `${origin}/${id}`) failures.push("share: the page's address or history changed");
    if (kept.storage.includes(id)) failures.push("share: the share's id is in the browser's storage");
    if (!packs.length || packs.some(pack => pack.status !== 200 || !/\bimmutable\b/.test(pack.cache))) {
      failures.push(`share: the model's packs were answered ${JSON.stringify(packs)}`);
    }
    // A face picked shows its facts, measured on the exact shape where it was shared: the part's table.
    const canvas = view.locator("canvas").first();
    const box = await canvas.boundingBox();
    await view.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
    const chip = view.locator("button", { hasText: /face \d+/ }).first();
    await chip.waitFor();
    await chip.click();
    const card = view.getByText(/[\d,.]+ mm²/).first();
    await card.waitFor();
    const area = await card.innerText();
    if (!/\d/.test(area)) failures.push(`share: a face's area reads ${JSON.stringify(area)}`);
    await view.keyboard.press("Escape");
    // Parameters are shown and read only: the page has no engine to save them, and its controls and Save say so.
    await view.locator("[data-flat-panel]").getByRole("tab", { name: "Params", exact: true }).click();
    const width = view.locator("[data-parameter=\"width\"]");
    await width.waitFor();
    const widthReason = await width.getAttribute("data-parameter-reason");
    if (widthReason !== "unavailable") failures.push(`share: the width parameter's reason is ${JSON.stringify(widthReason)}, not that this view can't save`);
    if (!(await view.locator("button[data-parameters-save]").isDisabled())) failures.push("share: Save is offered over a shared model");
    const saveReason = await view.locator("[data-parameters-save-reason]").getAttribute("data-parameters-save-reason");
    if (saveReason !== "unavailable") failures.push(`share: Save is off for ${JSON.stringify(saveReason)}, not because this view can't save`);
    await close(view, "view");

    // An address that names no share opens nothing: the service holds none, and the page says so.
    const unknown = await open(`/${randomBytes(16).toString("base64url")}`, { gone: true });
    await unknown.locator('[data-share-state="gone"]').waitFor();
    await close(unknown, "unknown");

    // The delete page asks, then sends the deletion with the secret in its Authorization alone.
    const remove = await open(`/${id}#delete=${secret}`);
    await remove.locator('[data-share-state="ask"]').waitFor();
    const deletes = () => asked.filter(request => request.method === "DELETE");
    if (deletes().length) failures.push("share: the delete page deleted before it was asked to");
    await remove.locator("[data-share-delete]").click();
    await remove.locator('[data-share-state="deleted"]').waitFor();
    const [deletion, ...more] = deletes();
    if (!deletion || more.length || deletion.headers.authorization !== `Bearer ${secret}` || deletion.url !== `${origin}/v1/shares/${id}`) {
      failures.push(`share: the deletion was ${JSON.stringify(deletes().map(({ url, headers }) => ({ url, sent: headers.authorization === `Bearer ${secret}` })))}`);
    }
    await close(remove, "delete");

    // Once deleted (or expired), the service holds it no more, and the view says so.
    const gone = await open(`/${id}`, { gone: true });
    await gone.locator('[data-share-state="gone"]').waitFor();
    await close(gone, "gone");

    // The page asked its own origin alone: of the API, a share's manifest and packs, and one deletion; the
    // secret went in one header of one request.
    const away = asked.filter(request => new URL(request.url).origin !== origin);
    if (away.length) failures.push(`share: requests to another origin: ${away.map(request => request.url).join(", ")}`);
    for (const request of asked) {
      const { pathname, search } = new URL(request.url);
      // What needs an engine is never asked: nothing under /api/.
      if (pathname.startsWith("/api/")) failures.push(`share: the page asked for ${pathname}, which needs an engine`);
      if (pathname.startsWith("/v1/") && (search || !/^\/v1\/shares\/[A-Za-z0-9_-]{22}(?:\/packs\/[0-9a-f]{64})?$/.test(pathname)
        || !(request.method === "GET" || (request.method === "DELETE" && pathname === `/v1/shares/${id}`)))) {
        failures.push(`share: the page asked the service ${request.method} ${pathname.replace(id, "<id>")}${search}`);
      }
      const said = `${request.url} ${JSON.stringify(request.headers)} ${request.body}`;
      const header = request.method === "DELETE" && request.headers.authorization === `Bearer ${secret}`;
      if (said.includes(secret) && !(header && !`${request.url} ${request.body}`.includes(secret)
        && Object.entries(request.headers).every(([name, value]) => name === "authorization" || !value.includes(secret)))) {
        failures.push(`share: the delete secret was sent outside the DELETE's Authorization: ${request.method} ${request.url}`);
      }
    }
    if (asked.filter(request => request.method === "DELETE").length !== 1) failures.push("share: the page sent more than one deletion");
    if (logged.some(text => text.includes(secret))) failures.push("share: the delete secret was logged");
    // The service's policy is all the page needs.
    for (const violation of violations) console.log(`  share: content security policy: ${JSON.stringify(violation)}`);
    if (violations.length) failures.push(`share: ${violations.length} content security policy violations`);
    if (errors.length) failures.push(`share: ${errors.join(" | ")}`);
  } finally {
    await context.close();
  }
  if (args.shareBoard || args.shareSchematic) await kicadShares();
}

// The board's view settings, the navbar's Display: its card's Side, and on the engine's page its Mode, 2D or 3D.
const DISPLAY = "[data-navbar-view-controls] [data-display-settings]";

async function kicadShares() {
  // A KiCad board and schematic shared as the model is (`--share-board`, `--share-schematic`: what `cad share --json`
  // printed), opened from the share service with no engine: the board drawn on its canvas in 2D alone, though its LED
  // stands on a STEP its project holds (a share shows a board in 2D: its 3D is a GLB of its own); the schematic's root
  // sheet, then the sheet the Hierarchy shows, read on its own.
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1 });
  const asked = [];
  context.on("request", (request) => asked.push(new URL(request.url()).pathname));
  const errors = [];
  try {
    for (const [what, file] of [["board", args.shareBoard], ["schematic", args.shareSchematic]]) {
      if (!file) continue;
      const shared = JSON.parse(fs.readFileSync(file, "utf8"));
      if (shared.ok !== true || typeof shared.view !== "string") {
        failures.push(`share: --share-${what} names no share the command made: ${file}`);
        continue;
      }
      const page = await context.newPage();
      page.setDefaultTimeout(120_000);
      page.on("pageerror", (error) => errors.push(`${what}: ${error.message || error}`));
      page.on("console", (message) => { if (message.type() === "error") errors.push(`${what}: console: ${message.text()}`); });
      await page.goto(shared.view, { waitUntil: "domcontentloaded" });
      if (what === "board") {
        await page.locator('[data-board-surface] [aria-busy="false"][data-board-settled="true"]').first().waitFor();
        // Display's card has the board's Side and no Mode, and the navbar no Preview.
        const card = page.locator("[data-display-settings-card]");
        await page.locator(DISPLAY).click();
        await card.locator('[data-settings-select="side"]').waitFor();
        if (await card.locator('[data-settings-select="dimension"]').count()) failures.push("share: the shared board's Display offers 2D/3D");
        await card.getByRole("button", { name: "Close display settings", exact: true }).click();
        await card.waitFor({ state: "detached" });
        if (await page.locator("[data-navbar-view-controls]").getByRole("button", { name: "Preview", exact: true }).count()) {
          failures.push("share: the shared board offers Preview");
        }
        // 3, which draws a board in 3D on the engine's page, does nothing here: ⇧F after it turns the board over, in 2D.
        await page.locator("[data-board-surface] canvas[role=img]").click();
        await page.keyboard.press("3");
        await page.keyboard.press("Shift+F");
        await page.locator(`${DISPLAY}[data-view-side="bottom"]`).waitFor();
        if (await page.locator("[data-board-3d]").count()) failures.push("share: 3 drew the shared board in 3D");
      } else {
        await page.locator('[data-schematic-sheet="/"]').waitFor();
        await page.locator('[data-schematic-surface] [aria-busy="false"][data-board-settled="true"]').first().waitFor();
        await page.locator("[data-flat-panel]").getByRole("tab", { name: "Hierarchy", exact: true }).click();
        await page.locator('[data-schematic-sheet-row="/Load/"] button').first().click();
        await page.locator('[data-schematic-sheet="/Load/"]').waitFor();
        await page.locator('[data-schematic-surface] [aria-busy="false"][data-board-settled="true"]').first().waitFor();
      }
      if (await page.title() !== shared.document.name) failures.push(`share: the shared ${what} is titled ${JSON.stringify(await page.title())}, not its file's name`);
      if (diagnosticDir) {
        fs.mkdirSync(diagnosticDir, { recursive: true });
        await page.screenshot({ path: path.join(diagnosticDir, `diagnostic-share-${what}.png`), timeout: 3000 }).catch(() => {});
      }
      await page.close();
    }
    // What needs an engine is never asked: nothing under /api/.
    for (const pathname of asked) if (pathname.startsWith("/api/")) failures.push(`share: a KiCad share's page asked for ${pathname}, which needs an engine`);
    if (errors.length) failures.push(`share: ${errors.join(" | ")}`);
  } finally {
    await context.close();
  }
}

// Every gate here runs in CI; there is no local-only set. Each assertion settles
// on published state rather than a frame rate or a sleep toward a conclusion, so a
// slow software-GL runner is slower, not redder. Picking parts, faces and robot
// links, and driving URDF joints and STEP mates, belong to the packages/ui browser
// specs.
// Each gate runs where its input is given: the runner hands the engine's page's gates their server, and
// the share gate its share once that server has stopped.
const gates = [
  ["format", formatGate, "url"],
  ["camera", modeCameraGate, "url"],
  ["prompt", promptGate, "plate"],
  ["share", shareGate, "share"],
];

if (args.only && !gates.some(([name]) => name === args.only)) fail(`unknown --only gate: ${args.only} (${gates.map(([name]) => name).join(", ")})`);
const selected = gates.filter(([name, , needs]) => (!args.only || name === args.only) && args[needs]);
if (!selected.length) fail(`the ${args.only} gate needs --${gates.find(([name]) => name === args.only)[2]}`);
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

