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
  const args = { url: "", dir: "", out: "" };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === "--url") args.url = argv[++i] || "";
    else if (flag === "--dir") args.dir = argv[++i] || "";
    else if (flag === "--out") args.out = argv[++i] || "";
    else throw new Error(`unknown argument: ${flag}`);
  }
  return args;
}

const args = parseArgs(process.argv.slice(2));
const root = path.resolve(args.dir || ".");
const fixtures = [
  { format: "stl", file: "smoke.stl", parts: false },
  { format: "3mf", file: "smoke.3mf", parts: false },
  { format: "glb", file: "smoke.glb", parts: false },
  { format: "step", file: "assembly.step", parts: true },
  { format: "dxf", file: "smoke.dxf", parts: false },
  { format: "urdf", file: "smoke.urdf", parts: false },
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
  await page.waitForTimeout(1000);
  return canvas;
}

function isHighlight(data, offset) {
  const r = data[offset];
  const g = data[offset + 1];
  const b = data[offset + 2];
  return b > 140 && b - r > 40 && g > 100 && g < 230;
}

function highlightComponents(png, mode = "face") {
  const step = mode === "edge" ? 1 : 2;
  const width = Math.floor(png.width / step);
  const height = Math.floor(png.height / step);
  let mask = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) for (let x = 0; x < width; x += 1) {
    if (isHighlight(png.data, ((y * step) * png.width + x * step) * 4)) mask[y * width + x] = 1;
  }
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

async function pickingGate(tag, lod) {
  const { context, page, errors } = await newPage({ lod });
  try {
    const canvas = await openFile(page, "smoke.step");
    const box = await canvas.boundingBox();
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    await page.mouse.move(cx, cy);
    await page.mouse.wheel(0, -120);
    await page.waitForTimeout(1200);

    const edgeHits = new Map();
    const probePoints = [];
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
        await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
        // Desktop activation is deliberately delayed 220ms to distinguish a
        // double click. Settle that one interaction, then make chip lookup
        // immediate; an absent chip must not add another locator timeout.
        await page.waitForTimeout(240);
        const ref = await chipRef(page);
        if (!/\.e\d+$/.test(ref)) continue;
        if (!edgeHits.has(ref)) edgeHits.set(ref, []);
        edgeHits.get(ref).push([fx, fy]);
        const hits = edgeHits.get(ref);
        const separated = hits.some(([x1, y1]) => hits.some(([x2, y2]) => Math.hypot(x2 - x1, y2 - y1) >= 0.08));
        // Toggle this exact hit off before the next probe. Otherwise an empty
        // click can leave the previous chip visible and manufacture repeats.
        await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
        await page.waitForTimeout(240);
        if (await chipRef(page)) fail(`${tag}: clicking ${ref} twice did not clear the selection`);
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
    await page.mouse.click(box.x + box.width * spots[0][0], box.y + box.height * spots[0][1]);
    await page.waitForTimeout(400);
    const edge = highlightComponents(PNG.sync.read(await page.screenshot()), "edge");
    const top3 = (edge.sizes[0] || 0) + (edge.sizes[1] || 0) + (edge.sizes[2] || 0);
    if (edge.total < 60 || top3 / edge.total < 0.9) {
      fail(`${tag}: edge ${edgeRef} highlight fragmented (${edge.sizes.length} pieces over ${edge.total}px)`);
    }
    // Return to an empty selection before face probes, so a miss cannot inherit
    // the edge chip whose framebuffer was just checked.
    await page.mouse.click(box.x + box.width * spots[0][0], box.y + box.height * spots[0][1]);
    await page.waitForTimeout(240);
    if (await chipRef(page)) fail(`${tag}: edge selection did not clear before face probes`);

    for (let i = 0; i < 3; i += 1) {
      await page.mouse.wheel(0, -220);
      await page.waitForTimeout(400);
    }
    await page.waitForTimeout(2000);
    const lodEvents = await page.evaluate(() => window.__viewerTestLodEvents || []);
    if (lod && !lodEvents.length) fail(`${tag}: no LOD swap fired`);
    if (!lod && lodEvents.length) fail(`${tag}: LOD-off page emitted swaps`);

    let faceRef = "";
    for (const [fx, fy] of [[0.5, 0.5], [0.45, 0.5], [0.55, 0.5], [0.5, 0.4], [0.5, 0.6]]) {
      await page.mouse.click(box.x + box.width * fx, box.y + box.height * fy);
      await page.waitForTimeout(240);
      const ref = await chipRef(page);
      if (/\.f\d+$/.test(ref)) faceRef = ref;
      if (faceRef) break;
    }
    if (!faceRef) fail(`${tag}: no face pick landed on the rendered cylinder`);
    await page.waitForTimeout(400);
    const face = highlightComponents(PNG.sync.read(await page.screenshot()));
    const ratio = face.total ? (face.sizes[0] || 0) / face.total : 0;
    if (face.total < 300 || ratio < 0.97) {
      fail(`${tag}: face ${faceRef} highlight fragmented (${(ratio * 100).toFixed(1)}%, ${face.total}px)`);
    }
    if (errors.length) fail(`${tag}: ${errors.join(" | ")}`);
    console.log(`  ${tag}: ${lodEvents.length} LOD swap(s), face ${faceRef} ${(ratio * 100).toFixed(1)}% contiguous, edge ${edgeRef} coherent`);
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
  const tools = ["Select", "Pan", "Draw", "Orbit", "Copy screenshot"];
  const camera = ["Reset Zoom", "Zoom To Fit"];
  const tree = ["Show all", "Expand all", "Collapse all"];
  const presentTree = ["Expand all", "Collapse all"];
  for (const fixture of fixtures) {
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
      await page.waitForFunction(
        (follows) => window.__cadModelPlacement?.floorFollowsModel === follows,
        false,
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
        if (placement.floorFollowsModel !== false) failures.push(`${setting.id}: default floor moved away from the authored origin`);
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
  console.log(`  placement: authored [39,-3,-5]..[45,3,9], inspection grid at world z=0, Render floor-follow enabled`);
  console.log(`  scenes: overall framebuffer spread ${spread.toFixed(1)}/255, Render backdrop spread ${studioSpread.toFixed(1)}/255`);
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

try {
  await pickingGate("cold+lod", true);
  await pickingGate("warm+lod", true);
  await pickingGate("lod-off", false);
  await formatGate();
  await sceneGates();
  await qualityGate();
} finally {
  await browser.close();
}

for (const result of results) console.log(`  ${result.format.padEnd(5)} framebuffer coverage ${result.coverage.toFixed(4)}`);
if (failures.length) {
  console.error("viewer browser failures:");
  for (const failure of failures) console.error(`  - ${failure}`);
  process.exit(1);
}
console.log(`viewer browser e2e: PASS (${fixtures.length} formats, 3 picking paths, 4 placement/appearance scenes, 2 quality cycles)`);
