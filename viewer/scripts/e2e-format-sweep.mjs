#!/usr/bin/env node
// Load one fixture per render format through a running CAD Viewer and assert each one
// actually draws something, with no page errors.
//
// This is the standing gate for viewer work that touches shared code: the whole point of
// the capability registry is that a change to one format reaches the others, which also
// means a mistake in shared code breaks all of them at once. Screenshot-based because a
// blank-but-error-free viewport is the signature failure here — a shader that fails to
// compile, or a gate that hides the geometry, both throw nothing.
//
// Reads the REAL framebuffer via page.screenshot(). Do NOT sample the canvas with
// drawImage: the drawing buffer is not preserved, so every format reports blank.
//
// Usage:
//   node viewer/scripts/e2e-format-sweep.mjs --dir <models-root> [--url http://127.0.0.1:3245]
//                                            [--all-implicits] [--out <dir>]
//
// Asserts, per format: the viewport is not blank, no page errors, the whole viewport tool
// cluster is present and usable, and the right-click viewport menu offers the camera
// actions (with assembly-tree entries only where the `parts` capability is declared).
//
// Requires a viewer already serving <models-root> (npm run start) and
// playwright available. Exits non-zero on the first failing format.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

function parseArgs(argv) {
  const args = { url: "http://127.0.0.1:3245", dir: "", out: "", allImplicits: false };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === "--url") args.url = argv[++index] || args.url;
    else if (flag === "--dir") args.dir = argv[++index] || "";
    else if (flag === "--out") args.out = argv[++index] || "";
    else if (flag === "--all-implicits") args.allImplicits = true;
  }
  return args;
}

// One fixture per format family. Kept small on purpose: this runs on every shared-code
// change, so it has to stay fast enough that people actually run it.
//
// `parts` is the capability that decides whether the viewport menu carries assembly-tree
// entries; everything else must show the camera section and nothing else.
const FIXTURES = [
  { format: "stl", file: "fun/miniature_spiral_staircase_highres.stl", parts: false },
  { format: "3mf", file: "fun/miniature_spiral_staircase_highres.3mf", parts: false },
  { format: "glb", file: "fun/miniature_spiral_staircase_highres.glb", parts: false },
  { format: "step", file: "simple/cam_follower_roller.step.py", parts: true },
  { format: "dxf", file: "dxf/alu_extrusion_profile.dxf", parts: false },
  { format: "implicit", file: "implicits/rounded-orb.implicit.js", parts: false },
  // The robot family had no fixture here at all, which is how it kept missing features
  // nobody was looking at. Needs `git lfs checkout models/robots/so101` first, like the
  // mesh and DXF fixtures.
  { format: "urdf", file: "robots/so101/so101.urdf", parts: false }
];

// Select, pan and draw act on the VIEWPORT, so every format gets them. They were off for
// plain meshes and for robots until the capability rows were made uniform: opening an STL
// lost three buttons that have nothing to do with what the file contains.
const VIEWPORT_TOOL_LABELS = ["Select", "Pan", "Draw", "Orbit", "Copy screenshot"];

async function toolProblem(page) {
  const missing = [];
  const disabled = [];
  for (const label of VIEWPORT_TOOL_LABELS) {
    const button = page.locator(`button[aria-label="${label}"]`).first();
    if (!(await button.count())) {
      missing.push(label);
      continue;
    }
    if (!(await button.isEnabled())) disabled.push(label);
  }
  if (missing.length) return `toolbar is missing ${missing.join(", ")}`;
  // Disabled is legitimate only while there is nothing on screen; the caller has already
  // asserted the viewport is not blank by this point.
  if (disabled.length) return `toolbar has ${disabled.join(", ")} disabled with content on screen`;
  return "";
}

// Camera actions are viewport-level, so every format's right-click menu must offer them.
// They were STEP-only until U3, and the failure was invisible: right-clicking simply did
// nothing on five of six formats.
const CAMERA_ACTIONS = ["Reset Zoom", "Zoom To Fit"];
const TREE_ACTIONS = ["Show all", "Expand all", "Collapse all"];

// A fixed screen coordinate silently tests the file sheet instead of the viewport on any
// format whose sheet has content, so resolve a point that is really over the canvas.
async function emptyCanvasPoint(page) {
  return page.evaluate(() => {
    const biggest = [...document.querySelectorAll("canvas")]
      .map((canvas) => canvas.getBoundingClientRect())
      .filter((rect) => rect.width > 200 && rect.height > 200)
      .sort((a, b) => b.width * b.height - a.width * a.height)[0];
    if (!biggest) return null;
    const x = Math.round(biggest.left + biggest.width * 0.12);
    const y = Math.round(biggest.top + biggest.height * 0.86);
    return { x, y, tag: document.elementFromPoint(x, y)?.tagName || "" };
  });
}

async function viewportMenuItems(page) {
  const point = await emptyCanvasPoint(page);
  if (point?.tag !== "CANVAS") return null;
  await page.mouse.move(point.x, point.y);
  await page.mouse.down({ button: "right" });
  await page.mouse.up({ button: "right" });
  await page.waitForTimeout(800);
  const menu = page.locator('[role="menu"]').first();
  const items = (await menu.count())
    ? (await menu.locator('[role="menuitem"]').allTextContents()).map((text) => text.trim())
    : [];
  await page.keyboard.press("Escape");
  await page.waitForTimeout(200);
  return items;
}

function menuProblem(items, fixture) {
  if (items === null) return "no canvas under the probe point";
  if (!items.length) return "viewport menu did not open";
  const missing = CAMERA_ACTIONS.filter((action) => !items.includes(action));
  if (missing.length) return `menu missing ${missing.join(", ")} (got: ${items.join(", ")})`;
  if (!fixture.parts) {
    const leaked = TREE_ACTIONS.filter((action) => items.includes(action));
    if (leaked.length) return `menu offers ${leaked.join(", ")} without the parts capability`;
  }
  return "";
}

// Below this fraction of non-background pixels the viewport is effectively empty.
const MIN_COVERAGE = 0.005;
const VIEWPORT = { width: 1440, height: 900 };
const CLIP = { x: 40, y: 60, width: 900, height: 760 };

function coverage(png) {
  const background = [png.data[0], png.data[1], png.data[2]];
  let covered = 0;
  let total = 0;
  for (let index = 0; index < png.data.length; index += 44) {
    total += 1;
    const delta = Math.abs(png.data[index] - background[0]) +
      Math.abs(png.data[index + 1] - background[1]) +
      Math.abs(png.data[index + 2] - background[2]);
    if (delta > 24) covered += 1;
  }
  return total ? covered / total : 0;
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

  const fixtures = [...FIXTURES];
  if (args.allImplicits) {
    const implicitDir = path.join(modelsRoot, "implicits");
    if (fs.existsSync(implicitDir)) {
      for (const name of fs.readdirSync(implicitDir).filter((f) => f.endsWith(".implicit.js"))) {
        const file = `implicits/${name}`;
        if (!fixtures.some((fixture) => fixture.file === file)) {
          fixtures.push({ format: "implicit", file });
        }
      }
    }
  }

  // --use-angle=metal: the software rasteriser shades differently and hides real GPU
  // failures, so a sweep run under SwiftShader is not evidence.
  const browser = await chromium.launch({ args: ["--use-angle=metal", "--ignore-gpu-blocklist"] });
  const page = await browser.newPage({ viewport: VIEWPORT, deviceScaleFactor: 1 });
  const results = [];

  for (const fixture of fixtures) {
    const errors = [];
    const onPageError = (error) => errors.push(String(error).slice(0, 200));
    const onConsole = (message) => {
      if (message.type() === "error") errors.push(message.text().slice(0, 200));
    };
    page.on("pageerror", onPageError);
    page.on("console", onConsole);

    // The model root is the URL PATH for this backend; a bare ?dir= alone resolves nothing.
    const url = `${args.url}${modelsRoot}?dir=${encodeURIComponent(modelsRoot)}` +
      `&file=${encodeURIComponent(fixture.file)}`;
    await page.goto(url, { waitUntil: "domcontentloaded" });
    // STEP builds its package on first open; everything else, robots included, is well
    // inside this window.
    await page.waitForTimeout(fixture.format === "step" ? 16000 : 9000);

    const buffer = await page.screenshot({ clip: CLIP });
    if (args.out) {
      fs.mkdirSync(args.out, { recursive: true });
      fs.writeFileSync(path.join(args.out, `${fixture.file.replace(/[^a-z0-9]/gi, "_")}.png`), buffer);
    }
    const covered = coverage(PNG.sync.read(buffer));
    const tools = covered < MIN_COVERAGE ? "" : await toolProblem(page);
    const menu = menuProblem(await viewportMenuItems(page), fixture);
    results.push({
      format: fixture.format,
      file: fixture.file,
      coverage: Number(covered.toFixed(4)),
      blank: covered < MIN_COVERAGE,
      tools,
      menu,
      errors: errors.slice(0, 3)
    });

    page.off("pageerror", onPageError);
    page.off("console", onConsole);
  }

  await browser.close();

  const failures = results.filter(
    (result) => result.blank || result.tools || result.menu || result.errors.length
  );
  for (const result of results) {
    const status = result.blank
      ? "BLANK"
      : result.tools
        ? "TOOLS"
        : result.menu
          ? "MENU"
          : result.errors.length ? "ERRORS" : "ok";
    console.log(`${status.padEnd(6)} ${result.format.padEnd(9)} cov=${result.coverage} ${result.file}`);
    if (result.tools) console.log(`         ${result.tools}`);
    if (result.menu) console.log(`         ${result.menu}`);
    for (const error of result.errors) console.log(`         ${error}`);
  }
  console.log(`\n${results.length - failures.length}/${results.length} formats rendered`);
  process.exit(failures.length ? 1 : 0);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
