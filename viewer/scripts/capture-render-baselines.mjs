#!/usr/bin/env node
// Visual baseline harness for the renderer-consolidation phases (see
// viewer/docs/renderer-consolidation.md). Unit tests do not exercise 3D
// rendering, so Phases 1-3 are gated on before/after screenshots: capture a
// labeled baseline before starting a phase, re-capture after, and eyeball the
// diff. This drives an ALREADY-RUNNING dev viewer (start it via the
// cad-viewer skill launcher) — it never starts or stops servers itself.
//
// Usage:
//   node viewer/scripts/capture-render-baselines.mjs \
//     --base-url http://127.0.0.1:4178 --label pre-phase-1a \
//     [--models-dir <abs path>] [--fixture <relative-to-models path>]... \
//     [--theme light]... [--wait-ms 9000] [--out-dir tmp/render-baselines]
//
// Defaults capture one implicit and one mesh fixture in light + dark. The
// mesh renderer has no preserveDrawingBuffer, so in-page canvas readback
// reads blank — the composited page.screenshot below is the trustworthy
// capture path.

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const DEFAULT_FIXTURES = [
  "implicits/parametric-pulse.implicit.js",
  "fun/miniature_spiral_staircase_highres.glb",
];
const DEFAULT_THEMES = ["light", "dark"];
// Implicit models need shader compile + auto-fit before the first real frame
// (~9s is the documented safe wait); meshes settle much faster but share the
// same wait for simplicity unless overridden.
const DEFAULT_WAIT_MS = 9000;

function parseArgs(argv) {
  const options = {
    baseUrl: "",
    label: "baseline",
    modelsDir: path.join(repoRoot, "models"),
    fixtures: [],
    themes: [],
    waitMs: DEFAULT_WAIT_MS,
    outDir: path.join(repoRoot, "tmp", "render-baselines"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = () => {
      index += 1;
      if (index >= argv.length) {
        throw new Error(`Missing value for ${arg}`);
      }
      return argv[index];
    };
    if (arg === "--base-url") options.baseUrl = next();
    else if (arg === "--label") options.label = next();
    else if (arg === "--models-dir") options.modelsDir = path.resolve(next());
    else if (arg === "--fixture") options.fixtures.push(next());
    else if (arg === "--theme") options.themes.push(next());
    else if (arg === "--wait-ms") options.waitMs = Number(next());
    else if (arg === "--out-dir") options.outDir = path.resolve(next());
    else throw new Error(`Unknown argument: ${arg}`);
  }
  if (!options.baseUrl) {
    throw new Error(
      "--base-url is required (start the viewer with the cad-viewer skill launcher and pass the URL it prints)"
    );
  }
  if (!options.fixtures.length) options.fixtures = [...DEFAULT_FIXTURES];
  if (!options.themes.length) options.themes = [...DEFAULT_THEMES];
  if (!Number.isFinite(options.waitMs) || options.waitMs < 0) {
    throw new Error("--wait-ms must be a non-negative number");
  }
  return options;
}

function resolvePlaywright() {
  // playwright is not a viewer dependency; it is vendored with implicitjs
  // (npm ci --prefix packages/implicitjs) for headless render tooling.
  const require = createRequire(import.meta.url);
  try {
    return require(path.join(repoRoot, "packages", "implicitjs", "node_modules", "playwright"));
  } catch {
    try {
      return require("playwright");
    } catch {
      throw new Error(
        "playwright not found. Run `npm ci --prefix packages/implicitjs` first (it vendors playwright)."
      );
    }
  }
}

function safeName(value) {
  return value.replace(/[^a-zA-Z0-9._-]+/gu, "_");
}

async function captureOne(browser, options, fixture, theme) {
  const url = new URL(options.baseUrl);
  url.searchParams.set("dir", options.modelsDir);
  url.searchParams.set("file", fixture);
  url.searchParams.set("theme", theme);

  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") {
      consoleErrors.push(message.text());
    }
  });
  try {
    await page.goto(url.toString(), { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForSelector("canvas", { timeout: 60000 });
    await page.waitForTimeout(options.waitMs);
    const outputPath = path.join(
      options.outDir,
      safeName(options.label),
      `${safeName(fixture)}__${safeName(theme)}.png`
    );
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    await page.screenshot({ path: outputPath });
    return { outputPath, consoleErrors };
  } finally {
    await page.close();
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const { chromium } = resolvePlaywright();
  const browser = await chromium.launch();
  const failures = [];
  try {
    for (const fixture of options.fixtures) {
      for (const theme of options.themes) {
        const target = `${fixture} [${theme}]`;
        try {
          const { outputPath, consoleErrors } = await captureOne(browser, options, fixture, theme);
          const errorNote = consoleErrors.length
            ? `  (${consoleErrors.length} console error(s): ${consoleErrors[0]})`
            : "";
          process.stdout.write(`captured ${target} -> ${path.relative(repoRoot, outputPath)}${errorNote}\n`);
          if (consoleErrors.length) {
            failures.push(`${target}: console errors during render`);
          }
        } catch (error) {
          failures.push(`${target}: ${error instanceof Error ? error.message : String(error)}`);
          process.stdout.write(`FAILED  ${target}\n`);
        }
      }
    }
  } finally {
    await browser.close();
  }
  if (failures.length) {
    process.stderr.write(`\n${failures.length} capture(s) failed or logged console errors:\n`);
    for (const failure of failures) {
      process.stderr.write(`  - ${failure}\n`);
    }
    process.exitCode = 1;
  }
}

main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 1;
});
