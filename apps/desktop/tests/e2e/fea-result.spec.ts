/**
 * An FEA result GLB in the explorer: `cadgen fea solve` writes it, the GLB
 * renderer shows the legend over it, and the legend's field switch and
 * deformation slider act on the mesh. The fixture is a build123d box solved
 * by the runtime's own cadgen at setup, so the file under test is exactly
 * what the command produces today, not a checked-in GLB that could drift.
 */
import fs from "node:fs";
import os from "node:os";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";
import { cadRuntimeReady, cadTestProfile, cadgenEnvironment } from "./cad-runtime";
import { openExplorerFile, selectFixtureSession } from "./session-fixture";

declare const window: { hardcore: HardcoreApi };

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
let env: NodeJS.ProcessEnv;
const errors: string[] = [];

const CANTILEVER_STEP_SCRIPT = `
import sys
from build123d import Align, Box, export_step
export_step(Box(60, 6, 6, align=(Align.MIN, Align.CENTER, Align.CENTER)), sys.argv[1])
`;

/** The result GLB, written by the runtime's cadgen; null when its fea extra is not installed. */
function writeFeaResult(python: string): string | null {
  const probe = execFileSync(python, ["-c", "import importlib.util as u; print(all(u.find_spec(m) for m in ('netgen', 'skfem', 'pyamg')))"], {
    env, encoding: "utf8", stdio: "pipe", timeout: 60_000,
  }).trim();
  if (probe !== "True") return null;
  const step = path.join(project, "beam.step");
  execFileSync(python, ["-c", CANTILEVER_STEP_SCRIPT, step], { cwd: project, env, stdio: "pipe", timeout: 120_000 });
  const faces = JSON.parse(execFileSync(python, ["-m", "cadgen.cli", "fea", "faces", step, "--json"], {
    cwd: project, env, encoding: "utf8", stdio: "pipe", timeout: 180_000,
  }).trim().split("\n").at(-1)!) as { faces: { ref: string; normal: number[] | null }[] };
  const fixed = faces.faces.find((face) => (face.normal?.[0] ?? 0) < -0.99)!.ref;
  const loaded = faces.faces.find((face) => (face.normal?.[0] ?? 0) > 0.99)!.ref;
  const study = JSON.stringify({
    material: "steel",
    fixtures: [{ faces: [fixed], type: "fixed" }],
    loads: [{ faces: [loaded], type: "force", vector_N: [0, 0, -100] }],
    mesh: { size_mm: 2.5 },
  });
  const out = path.join(project, "FEA", "beam.study1.glb");
  execFileSync(python, ["-m", "cadgen.cli", "fea", "solve", step, out, "--study", study, "--json"], {
    cwd: project, env, stdio: "pipe", timeout: 300_000,
  });
  return out;
}

test.describe.configure({ mode: "serial" });
test.beforeAll(async () => {
  project = fs.mkdtempSync(path.join(os.tmpdir(), "fea-result-"));
  userData = cadTestProfile("fea-result");
  env = cadgenEnvironment(userData);
  app = await electron.launch({
    args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${userData}`],
    env: { ...env, NODE_ENV: "test", HARDCORE_FAKE_AGENT: path.join(appRoot, "tests/fake-agent/index.mjs") },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  page.on("pageerror", (error) => errors.push(error.message));
  const runtime = await page.evaluate(() => window.hardcore.runtime.status());
  test.skip(!cadRuntimeReady(runtime), "CAD runtime required");
  if (!runtime.python) throw new Error("Ready CAD runtime has no Python interpreter");
  const glb = writeFeaResult(runtime.python);
  test.skip(!glb, "the runtime's cadgen has no fea extra (netgen, scikit-fem, pyamg)");
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1600, 900));
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark", reduceMotion: true, defaultGitMode: "none", fetchBeforeCreate: false }));
  await selectFixtureSession(page, project);
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await page.getByRole("button", { name: "Toggle explorer", exact: true }).click();
});

test.afterAll(async () => {
  try {
    await app?.close();
  } finally {
    for (const directory of [userData, project]) {
      if (directory) fs.rmSync(directory, { recursive: true, force: true });
    }
  }
});

test("a result GLB opens with its legend, and a plain STEP has none", async () => {
  await openExplorerFile(page, "beam.study1.glb");
  const legend = page.getByRole("group", { name: "FEA result" });
  await expect(legend).toBeVisible({ timeout: 30_000 });
  await expect(legend).toContainText("beam.step");
  // The colour bar's top tick carries the field's units, and the field select names the field.
  await expect(legend.getByRole("list", { name: /von Mises stress scale/ })).toContainText("MPa");
  await expect(legend.getByRole("combobox", { name: "Result field" })).toContainText("von Mises stress");
  await expect(legend.getByRole("textbox", { name: "Deformation scale value" })).toHaveValue(/^×\d/);
  expect(errors, errors.join("\n")).toEqual([]);

  await openExplorerFile(page, "beam.step");
  await expect(page.getByRole("group", { name: "FEA result" })).toHaveCount(0);
});

test("the field switch recolours to displacement in millimetres", async () => {
  await page.getByRole("tab", { name: /beam\.study1\.glb/ }).click();
  const legend = page.getByRole("group", { name: "FEA result" });
  await legend.getByRole("combobox", { name: "Result field" }).click();
  await page.getByRole("option", { name: "displacement" }).click();
  await expect(legend.getByRole("combobox", { name: "Result field" })).toContainText("displacement");
  await expect(legend.getByRole("list", { name: /displacement scale/ })).toContainText("mm");
  await page.screenshot({ path: test.info().outputPath("fea-displacement.png"), animations: "disabled" });
  expect(errors, errors.join("\n")).toEqual([]);
});

test("the deformation slider runs from the undeformed shape to four times the file's own scale", async () => {
  const legend = page.getByRole("group", { name: "FEA result" });
  const slider = legend.getByRole("slider", { name: "Deformation scale" });
  const value = legend.getByRole("textbox", { name: "Deformation scale value" });
  const initial = await value.inputValue();
  await slider.focus();
  await page.keyboard.press("Home");
  await expect(value).toHaveValue("×0");
  await page.keyboard.press("End");
  const atEnd = Number((await value.inputValue()).replace(/^×/, ""));
  expect(atEnd).toBeGreaterThanOrEqual(4 * Number(initial.replace(/^×/, "")) * 0.99);
  await page.screenshot({ path: test.info().outputPath("fea-max-deformation.png"), animations: "disabled" });
  expect(errors, errors.join("\n")).toEqual([]);
});
