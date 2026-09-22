import fs from "node:fs";
import os from "node:os";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test, type ElectronApplication, type Page, type Request } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from "./cad-runtime";
import { selectFixtureSession } from "./session-fixture";

declare const window: {
  hardcore: HardcoreApi;
  __cadDisplayRecords?: () => { partId: string; matrix: number[] | null }[];
  __cadModelPlacement?: { modelKey?: string };
  __cadViewerQuality?: { modelKey?: string; standardQualityReady?: boolean };
};
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const repoRoot = path.resolve(appRoot, "../..");
let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
const errors: string[] = [];
// Feature recognition runs in a packaged worker. A lone part is recognized as soon as its
// Features tab shows it, which is whichever test opens it first, so workers are counted from
// the app's start.
let recognitionWorkers = 0;
const MANY_COMPONENT_COUNT = 32;
const MANY_COMPONENT_STEP_SCRIPT = `
import sys
from pathlib import Path
import build123d as bd
from cadgen.step_export import export_build123d_step_file

parts = []
for index in range(${MANY_COMPONENT_COUNT}):
    size_x = 1.0 + index * 0.01
    size_y = 1.0 + (index % 3) * 0.02
    size_z = 1.0 + (index % 5) * 0.01
    part = bd.Box(size_x, size_y, size_z).moved(
        bd.Location(((index % 8) * 3.0, (index // 8) * 3.0, 0.0))
    )
    part.label = f"component_{index:02d}"
    parts.append(part)

export_build123d_step_file(
    bd.Compound(children=parts, label="many_components"),
    Path(sys.argv[1]),
)
`;

function writeManyComponentStep(python: string, output: string) {
  execFileSync(python, ["-c", MANY_COMPONENT_STEP_SCRIPT, output], {
    cwd: project,
    env: { ...process.env, ...cadRegistryEnvironment(userData), CADGEN_DAEMON: "0",
      CADGEN_CACHE_DIR: path.join(userData, "cad-cache"), CADGEN_DAEMON_STATE_DIR: path.join(userData, "cad-daemon") },
    stdio: "pipe",
    timeout: 120_000,
  });
}

test.describe.configure({ mode: "serial" });
test.beforeAll(async () => {
  // This project owns its tiny fixtures and never reads the shared models corpus.
  project = fs.mkdtempSync(path.join(os.tmpdir(), "cad-scenes-"));
  fs.copyFileSync(path.join(repoRoot, "tests/fixtures/cad/import-smoke.step"), path.join(project, "part.step"));
  const animatedStep = fs.readFileSync(path.join(project, "part.step"));
  fs.writeFileSync(path.join(project, "animated.step"), animatedStep);
  fs.writeFileSync(path.join(project, "animated.step.json"), JSON.stringify({
    schemaVersion: 9,
    documentHash: createHash("sha256").update(animatedStep).digest("hex"),
    animation: {
      language: "javascript",
      source: `export const clips = {
        slide: { label: "Slide", duration: 4, update(t, m) { m.get("smoke").translate([t, 0, 0]); } }
      };`,
    },
  }));
  fs.writeFileSync(path.join(project, "hinge.urdf"), `<?xml version="1.0"?>
<robot name="hinge">
  <link name="base"><visual><geometry><box size="0.1 0.1 0.04"/></geometry></visual></link>
  <link name="arm"><visual><origin xyz="0.1 0 0"/><geometry><box size="0.2 0.04 0.04"/></geometry></visual></link>
  <joint name="hinge" type="revolute"><parent link="base"/><child link="arm"/>
    <origin xyz="0 0 0.04"/><axis xyz="0 0 1"/><limit lower="-1.57" upper="1.57" effort="1" velocity="1"/>
  </joint>
</robot>`);
  userData = cadTestProfile("cad-scenes");
  app = await electron.launch({
    args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${userData}`],
    env: { ...process.env, ...cadRegistryEnvironment(userData), NODE_ENV: "test", HARDCORE_FAKE_AGENT: path.join(appRoot, "tests/fake-agent/index.mjs"),
      CADGEN_DAEMON: "0", CADGEN_CACHE_DIR: path.join(userData, "cad-cache"), CADGEN_DAEMON_STATE_DIR: path.join(userData, "cad-daemon") },
  });
  page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  page.on("pageerror", error => errors.push(error.message));
  page.on("worker", worker => { if (worker.url().includes("modelingTree.worker")) recognitionWorkers += 1; });
  page.on("console", message => { if (message.type() === "error") console.error(`[CAD renderer] ${message.text()}`); });
  page.on("response", async response => {
    if (response.status() >= 400 && /\/__(?:cad|tess_cache)(?:\/|\?)/.test(response.url())) {
      const error = `HTTP ${response.status()} ${response.url()}`;
      errors.push(error);
      console.error(`[CAD request] ${JSON.stringify({ status: response.status(), url: response.url(),
        request: response.request().postData(), response: (await response.text().catch(String)).slice(0, 4000) })}`);
    }
  });
  const runtime = await page.evaluate(() => window.hardcore.runtime.status());
  console.info(`[CAD runtime] ${JSON.stringify({ python: runtime.python, source: runtime.source, cadgenVersion: runtime.cadgenVersion })}`);
  test.skip(!cadRuntimeReady(runtime), "CAD runtime required");
  if (process.env.CAD_DESKTOP_PYTHON) expect(runtime.python).toBe(process.env.CAD_DESKTOP_PYTHON);
  if (!runtime.python) throw new Error("Ready CAD runtime has no Python interpreter");
  writeManyComponentStep(runtime.python, path.join(project, "many-a.step"));
  fs.copyFileSync(path.join(project, "many-a.step"), path.join(project, "many-b.step"));
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
    try {
      const runtimeLog = userData && path.join(userData, "cad-runtime.log");
      if (runtimeLog && fs.existsSync(runtimeLog)) fs.copyFileSync(runtimeLog, test.info().outputPath("cad-runtime.log"));
    } finally {
      try { if (userData) fs.rmSync(userData, { recursive: true, force: true }); }
      finally { if (project) fs.rmSync(project, { recursive: true, force: true }); }
    }
  }
});

async function openFile(file: string) {
  // Each session keeps its own explorer, and a session just made has its closed and empty
  // (`docs/session-workspaces.md`): open it first.
  const newTab = page.getByRole("button", { name: "New tab", exact: true });
  if (!(await newTab.isVisible())) {
    await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
    await page.getByRole("button", { name: "Toggle explorer", exact: true }).click();
  }
  await newTab.click();
  await page.getByRole("menuitem", { name: "File", exact: false }).click();
  await page.getByLabel("Filter files").fill(file);
  await page.getByRole("option", { name: file, exact: false }).first().click();
  await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible({ timeout: 90_000 });
  // Picked in the tree, the file opens with the tree still up; these tests are about the
  // file, so its own panel is taken up.
  await expect(page.getByTestId("tree-toggle")).toHaveAttribute("aria-pressed", "true");
  await showPanel("cad-file");
}

async function selectOrOpenFile(file: string) {
  const tab = page.getByRole("tab", { name: new RegExp(file.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) });
  if (await tab.count()) {
    await tab.click();
    await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible({ timeout: 90_000 });
    return;
  }
  await openFile(file);
}

/** A panel's toggle in the nav row, pressed only if its panel is not already the open one. */
async function showPanel(id: "cad-file" | "cad-display") {
  const toggle = page.locator(`header [data-file-panel=${id}]`);
  if (await toggle.getAttribute("aria-pressed") !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
}

async function setDisplayMode(mode: string) {
  // Display is a panel of its own, beside the file's: its toggle turns the column over to it.
  await showPanel("cad-display");
  const value = page.locator("[data-file-sheet=Display]").getByRole("combobox", { name: "Mode" });
  await value.click();
  await page.getByRole("option", { name: mode, exact: true }).click();
  await expect(value).toContainText(mode);
  // Retain the helper's original return to geometry inspection: the file's own panel.
  if (await page.locator("header [data-file-panel=cad-file]").count()) await showPanel("cad-file");
  // The file-session writer batches ordinary UI changes for 180ms.
  await page.waitForTimeout(250);
}

async function expectDisplayMode(mode: string) {
  await showPanel("cad-display");
  await expect(page.locator("[data-file-sheet=Display]")
    .getByRole("combobox", { name: "Mode" })).toContainText(mode);
  if (await page.locator("header [data-file-panel=cad-file]").count()) await showPanel("cad-file");
}

async function expectCadReady(file: string, componentCount = 1) {
  await expect.poll(async () => page.evaluate(({ expectedFile, expectedComponents }) => {
    const placement = window.__cadModelPlacement?.modelKey || "";
    const quality = window.__cadViewerQuality;
    return placement.includes(expectedFile)
      && String(quality?.modelKey || "").includes(expectedFile)
      && quality?.standardQualityReady === true
      && (window.__cadDisplayRecords?.().length || 0) >= expectedComponents;
  }, { expectedFile: file, expectedComponents: componentCount }), {
    timeout: 90_000,
  }).toBe(true);
  // Nothing is still covering the model as it opens.
  await expect(page.locator("[data-viewer-loading]")).toHaveCount(0);
  await expect(page.getByRole("status").filter({
    hasText: /Recognizing geometry|Loading model geometry/,
  })).toHaveCount(0);
  const model = page.getByRole("list", { name: "Model", exact: true });
  await expect(model).toBeVisible({ timeout: 15_000 });
  if (componentCount === 1) {
    // A lone part is presented as its features, so it is ready when they are listed.
    await expect(model.getByRole("button", { name: /^Select / }).first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Loading features…", { exact: true })).toHaveCount(0);
  }
}

/**
 * Select a lone part WHOLE. It has no row of its own in the Features tree, so it is selected
 * where a person selects a part whole: in the viewport, under the Select tool's Parts filter.
 */
async function selectWholePart() {
  await setSelectFilter(/^Parts/);
  const canvas = page.locator("[data-cad-surface] canvas").first();
  const box = (await canvas.boundingBox())!;
  await canvas.click({ position: { x: box.width / 2, y: box.height / 2 } });
  await expect(page.getByRole("region", { name: "Reference details", exact: true })).toBeVisible();
}

/** The Select tool's second press opens its filter; the filter is kept with the file. */
async function setSelectFilter(name: RegExp) {
  const select = page.getByRole("group", { name: "Interaction tools", exact: true }).getByRole("button", { name: "Select", exact: true });
  if (await select.getAttribute("aria-pressed") !== "true") await select.click();
  await expect(select).toHaveAttribute("aria-pressed", "true");
  await select.click();
  await page.getByRole("menuitemradio", { name }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
}

test("View presets preserve authored materials and independent tools without a Materials editor", async () => {
  test.setTimeout(150_000);
  await openFile("part.step");
  await expect(page.getByRole("list", { name: "Model", exact: true })).toBeVisible({ timeout: 90_000 });
  await selectWholePart();
  const materialInfo = page.locator('[aria-label="Source material"]');
  await expect(materialInfo).toContainText("Unassigned");
  await expect(materialInfo.locator("input, select, button")).toHaveCount(0);
  // Authored changes arrive through the watched sidecar, never a viewer editor.
  const occurrenceId = await page.evaluate(() => window.__cadDisplayRecords?.()[0]?.partId);
  expect(occurrenceId).toBeTruthy();
  fs.writeFileSync(path.join(project, "part.step.json"), JSON.stringify({
    schemaVersion: 9,
    documentHash: createHash("sha256").update(fs.readFileSync(path.join(project, "part.step"))).digest("hex"),
    appearance: {
      materials: { steel: { name: "Brushed steel", roughness: 0.25, metalness: 1 } },
      assignments: { [occurrenceId!]: "steel" },
    },
  }));
  await expect(materialInfo).toContainText("Brushed steel", { timeout: 30_000 });
  await expect(materialInfo).toContainText("25%");
  await page.screenshot({ path: test.info().outputPath("inspect-material.png"), animations: "disabled" });
  await page.keyboard.press("Escape");
  await page.screenshot({ path: test.info().outputPath("inspect-material-unselected.png"), animations: "disabled" });
  await expect(page.getByRole("button", { name: "Theme settings", exact: true })).toHaveCount(0);
  await expect(page.locator("[data-file-panel=cad-theme], [data-file-sheet=Theme]")).toHaveCount(0);
  // A lone part's own panel is named for it; Display is the panel beside it, and no panel
  // of a Materials or Studio editor is in the row.
  await expect(page.locator("header [data-file-panel]")).toHaveCount(3);
  expect(await page.locator("header [data-file-panel]").evaluateAll(toggles => toggles.map(toggle =>
    `${toggle.getAttribute("data-file-panel")}:${toggle.getAttribute("aria-label")}`)))
    .toEqual(["cad-file:Part", "cad-display:Display", "tree:Show files"]);
  const viewTab = page.locator("header [data-file-panel=cad-display]");
  const view = page.locator("[data-file-sheet=Display]");
  const mode = view.getByRole("combobox", { name: "Mode" });
  await viewTab.click();
  // The section rules of `packages/ui/docs/settings-ui.md`. Surfaces is always open: its
  // header is static text, 28px and regular 12px, with no disclosure, plus or minus.
  const surfaces = view.getByRole("region", { name: "Surfaces", exact: true });
  const surfacesHeading = surfaces.getByRole("heading", { name: "Surfaces", exact: true });
  await expect(surfacesHeading).toBeVisible();
  await expect(surfaces.getByRole("button", { name: /Surfaces$/ })).toHaveCount(0);
  expect((await surfacesHeading.boundingBox())?.height).toBe(28);
  expect(await surfacesHeading.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element).fontSize)).toBe("12px");
  await expect(view.getByRole("button", { name: "View", exact: true })).toHaveCount(0);
  await expect(view.getByRole("combobox", { name: "Projection", exact: true })).toBeVisible();
  // Clip is optional and off: its title is the control that turns it on, and hovering its
  // header gives the row a gray background and nothing else.
  const clip = view.getByRole("button", { name: "Clip", exact: true });
  await expect(clip).toHaveAttribute("aria-expanded", "false");
  await expect(clip.locator("svg")).toHaveCount(0);
  expect((await clip.boundingBox())?.height).toBe(28);
  expect(await clip.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element).fontSize)).toBe("12px");
  const restingBackground = await clip.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element.parentElement!.parentElement!).backgroundColor);
  await clip.hover();
  await expect.poll(() => clip.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element).textDecorationLine)).not.toContain("underline");
  await expect.poll(() => clip.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element.parentElement!.parentElement!).backgroundColor)).not.toBe(restingBackground);
  await clip.click();
  // Open, Clip is a position along each axis and a flip.
  for (const axis of ["X", "Y", "Z"]) await expect(view.getByLabel(`Clip ${axis} position`, { exact: true })).toBeVisible();
  await expect(view.getByRole("checkbox", { name: "Flip", exact: true })).toBeVisible();
  await mode.click();
  await page.getByRole("option", { name: "Wireframe", exact: true }).click();
  await expect(mode).toContainText("Wireframe");
  await expect(page.getByRole("region", { name: "Materials", exact: true })).toHaveCount(0);

  await mode.click();
  await page.getByRole("option", { name: "Render", exact: true }).click();
  await expect(viewTab).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("button", { name: "Theme settings", exact: true })).toHaveCount(0);
  // Render turns Lighting on. Open, its header is text and only its minus is a control.
  const disableLighting = view.getByRole("button", { name: "Disable Lighting", exact: true });
  await expect(disableLighting).toHaveAttribute("aria-expanded", "true");
  await expect(view.getByRole("button", { name: "Lighting", exact: true })).toHaveCount(0);
  const exposure = view.getByLabel("Exposure value", { exact: true });
  await expect(view.getByRole("combobox", { name: "Quality", exact: true })).toContainText("Preview");
  await exposure.fill("1.5");
  await exposure.press("Enter");
  await expect(mode).toContainText("Custom");
  await disableLighting.click();
  await expect(exposure).toHaveCount(0);
  await expect(mode).toBeVisible();
  // Closed, its title is the control that turns it back on, at its defaults.
  await view.getByRole("button", { name: "Lighting", exact: true }).click();
  await expect(exposure).toHaveValue("0.0 EV");
  await exposure.fill("1.5");
  await exposure.press("Enter");
  await expect(page.getByRole("region", { name: "Materials", exact: true })).toHaveCount(0);
  await expect(page.locator("[data-cad-materials-settings-section]")).toHaveCount(0);
  await expect(page.locator("[data-file-panel-container]")).toHaveCount(1);
  await page.screenshot({ path: test.info().outputPath("render-view.png"), animations: "disabled" });

  await mode.click();
  await page.getByRole("option", { name: "Wireframe", exact: true }).click();
  await expect(viewTab).toHaveAttribute("aria-pressed", "true");
  // Wireframe has no lighting: the section is closed, its title the control that opens it.
  await expect(view.getByRole("button", { name: "Lighting", exact: true })).toHaveAttribute("aria-expanded", "false");
  await expect(exposure).toHaveCount(0);
  await expect(view.getByLabel("Clip X position", { exact: true })).toBeVisible();
  await expect(page.getByRole("region", { name: "Studio", exact: true })).toHaveCount(0);
  await mode.click();
  await page.getByRole("option", { name: "Render", exact: true }).click();
  await expect(exposure).toHaveValue("0.0 EV");
  await mode.click();
  await page.getByRole("option", { name: "Solid", exact: true }).click();
  // Leaving Render prepares the view again; a pick waits until the model is ready for one.
  await expect(page.locator("[data-viewer-transition]")).toHaveCount(0);
  await page.locator("header [data-file-panel=cad-file]").click();
  await expectCadReady("part.step");
  await selectWholePart();
  await expect(materialInfo).toContainText("Brushed steel");
  const sidecarPath = path.join(project, "part.step.json");
  const sidecar = JSON.parse(fs.readFileSync(sidecarPath, "utf8"));
  delete sidecar.appearance;
  fs.writeFileSync(sidecarPath, JSON.stringify(sidecar));
  await expect(materialInfo).toContainText("Unassigned", { timeout: 30_000 });
  await page.keyboard.press("Escape");
  await setSelectFilter(/^All/);
  expect(await page.evaluate(() => localStorage.getItem("cad-viewer:theme"))).toBeNull();
  expect(errors).toEqual([]);
});

test("robot Position edits, preserves and resets a joint through the robot's own panel", async () => {
  await openFile("hinge.urdf");
  // A robot's own panel is named for what it is, and its joints are the Position section at
  // the top of it: one section, with no Joints section inside it.
  await expect(page.locator("[data-file-sheet=Robot]")).toBeVisible();
  await expect(page.locator("header [data-file-panel=cad-file]")).toHaveAttribute("aria-label", "Robot");
  const position = page.getByRole("region", { name: "Position", exact: true });
  await expect(position).toBeVisible();
  await expect(position.getByRole("heading", { name: "Joints", exact: true })).toHaveCount(0);
  const joint = page.getByLabel("hinge value in deg", { exact: true });
  await expect(joint).toHaveValue("0°");
  await joint.fill("35");
  await joint.press("Enter");
  await expect(joint).toHaveValue("35°");
  await page.getByRole("button", { name: "Show files", exact: true }).click();
  await expect(joint).toBeHidden();
  await page.locator("header [data-file-panel=cad-file]").click();
  await expect(joint).toHaveValue("35°");
  await page.getByRole("button", { name: "Reset", exact: true }).click();
  await expect(joint).toHaveValue("0°");
  await page.screenshot({ path: test.info().outputPath("robot-kinematics.png"), animations: "disabled" });
  expect(errors).toEqual([]);
});

test("embedded STEP animation loads, plays and scrubs under the desktop CSP", async () => {
  // Keep the ordinary UI budget separate from the existing cold CAD-load wait.
  test.setTimeout(60_000 + 90_000);
  await openFile("animated.step");
  // A routine and no mates: nothing to pose, so no Position section and no Position tool.
  // Playback is the Animate tool, whose playbar sits under the model while it is up.
  const tools = page.getByRole("group", { name: "Interaction tools", exact: true });
  await expect(tools.getByRole("button", { name: "Animate", exact: true })).toBeVisible();
  await expect(tools.getByRole("button", { name: "Position", exact: true })).toHaveCount(0);
  await expect(page.getByRole("region", { name: "Position", exact: true })).toHaveCount(0);
  await tools.getByRole("button", { name: "Animate", exact: true }).click();
  const animation = page.getByRole("toolbar", { name: "Animation playback", exact: true });
  const play = animation.getByRole("button", { name: "Play animation", exact: true });
  // The data: module regression renders an error in place of these controls.
  await expect(play).toBeEnabled();
  const time = animation.getByRole("slider", { name: "Animation time", exact: true });
  await expect(time).toHaveAttribute("aria-valuenow", "0");

  await expect.poll(async () => page.evaluate(() => window.__cadDisplayRecords?.().length || 0)).toBeGreaterThan(0);
  const rest = await page.evaluate(() => window.__cadDisplayRecords?.()[0]);
  expect(rest?.matrix).toHaveLength(16);
  if (!rest?.matrix) throw new Error("Animated STEP did not publish a display transform");
  const restX = rest.matrix[12]!;
  const displayMatrix = () => page.evaluate(partId => (
    window.__cadDisplayRecords?.().find(record => record.partId === partId)?.matrix || null
  ), rest.partId);

  await play.click();
  await expect.poll(async () => Number(await time.getAttribute("aria-valuenow"))).toBeGreaterThan(0.05);
  await expect.poll(async () => (await displayMatrix())?.[12] ?? restX).toBeGreaterThan(restX + 0.05);
  await animation.getByRole("button", { name: "Pause animation", exact: true }).click();
  await expect(play).toBeVisible();

  // Scrubbing is the slider: a hundredth of a second a step, a tenth a page. At 1.25 s the clip
  // (which slides 1 a second) has moved the model 1.25, and the slider's start is the restart:
  // the model exactly at rest again.
  await time.focus();
  await page.keyboard.press("Home");
  for (let tenth = 0; tenth < 12; tenth += 1) await page.keyboard.press("PageUp");
  for (let hundredth = 0; hundredth < 5; hundredth += 1) await page.keyboard.press("ArrowRight");
  await expect(time).toHaveAttribute("aria-valuenow", "1.25");
  // Read the existing diagnostic seam's live mesh matrix, not just transport state.
  await expect.poll(async () => (await displayMatrix())?.[12] ?? restX).toBeCloseTo(restX + 1.25, 6);
  await page.screenshot({ path: test.info().outputPath("embedded-step-animation.png"), animations: "disabled" });
  await page.keyboard.press("Home");
  await expect(time).toHaveAttribute("aria-valuenow", "0");
  await expect.poll(displayMatrix).toEqual(rest.matrix);
  // Leaving Animate takes the playbar down and leaves the model at rest.
  await tools.getByRole("button", { name: "Select", exact: true }).click();
  await expect(animation).toHaveCount(0);
  await expect.poll(displayMatrix).toEqual(rest.matrix);

  const policy = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute("content");
  const scriptSources = policy?.split(";").map(directive => directive.trim().split(/\s+/))
    .find(([directive]) => directive === "script-src")?.slice(1);
  // Permit the document's in-memory module and compiled WASM without enabling
  // data:, unrestricted JavaScript eval or remote scripts.
  expect(scriptSources).toEqual(["'self'", "'wasm-unsafe-eval'", "blob:"]);
  expect(errors).toEqual([]);
});

test("reopening a many-component STEP reuses its backend and every prepared body", async () => {
  test.setTimeout(150_000);
  type RecordedRequest = {
    method: string; origin: string; pathname: string; file: string; surfaceInput: string; object: string;
  };
  const requests: RecordedRequest[] = [];
  const activeBodyRequests = new Set<Request>();
  let lastBodyActivityAt = Date.now();
  const isBodyRequest = (request: RecordedRequest) => {
    if (request.pathname === "/__cad/asset" && /\.step(?:\.json)?$/i.test(request.file)) return true;
    if (request.pathname === "/__cad/store" && request.surfaceInput) return true;
    return request.pathname.startsWith("/__tess_cache/")
      && request.pathname !== "/__tess_cache/probe";
  };
  const requestFacts = (request: Request): RecordedRequest => {
    const url = new URL(request.url());
    return {
      method: request.method(),
      origin: url.origin,
      pathname: url.pathname,
      file: url.searchParams.get("file") || "",
      surfaceInput: url.searchParams.get("surfaceInput") || "",
      object: url.searchParams.get("object") || "",
    };
  };
  const recordRequest = (request: Request) => {
    const facts = requestFacts(request);
    if (!facts.pathname.startsWith("/__cad/") && !facts.pathname.startsWith("/__tess_cache/")) return;
    requests.push(facts);
    if (isBodyRequest(facts)) {
      activeBodyRequests.add(request);
      lastBodyActivityAt = Date.now();
    }
  };
  const finishRequest = (request: Request) => {
    if (activeBodyRequests.delete(request)) lastBodyActivityAt = Date.now();
  };
  const expectBodyRequestsDrained = async () => {
    await expect.poll(() => activeBodyRequests.size === 0 && Date.now() - lastBodyActivityAt >= 300, {
      timeout: 30_000,
    }).toBe(true);
  };
  page.on("request", recordRequest);
  page.on("requestfinished", finishRequest);
  page.on("requestfailed", finishRequest);
  try {
    // These documents have the same STEP bytes but distinct per-file state: each keeps its
    // own display mode (X-ray is material only, so it asks for no geometry of its own).
    // Warm both before measuring the A -> B -> A reopen path.
    await selectOrOpenFile("many-a.step");
    await expectCadReady("many-a.step", MANY_COMPONENT_COUNT);
    await setDisplayMode("Wireframe");
    await expectCadReady("many-a.step", MANY_COMPONENT_COUNT);
    await selectOrOpenFile("many-b.step");
    await expectCadReady("many-b.step", MANY_COMPONENT_COUNT);
    await setDisplayMode("X-ray");
    await expectCadReady("many-b.step", MANY_COMPONENT_COUNT);
    await selectOrOpenFile("many-a.step");
    await expectCadReady("many-a.step", MANY_COMPONENT_COUNT);
    await expectDisplayMode("Wireframe");
    await expect(page.locator("[data-cad-surface]")).toHaveCount(1);
    await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible();

    // The shared cache defers its best-effort first write for 1.5s. Drain that
    // cold-load write before measuring so a later POST means new tessellation.
    await page.waitForTimeout(1_700);
    await expectBodyRequestsDrained();

    const measuredAt = requests.length;
    const transitionStartedAt = Date.now();
    await selectOrOpenFile("many-b.step");
    await expectCadReady("many-b.step", MANY_COMPONENT_COUNT);
    await expectDisplayMode("X-ray");
    await expect(page.locator("[data-cad-surface]")).toHaveCount(1);
    await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible();
    await selectOrOpenFile("many-a.step");
    await expectCadReady("many-a.step", MANY_COMPONENT_COUNT);
    await expectDisplayMode("Wireframe");
    await expect(page.locator("[data-cad-surface]")).toHaveCount(1);
    await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible();
    const switchElapsedMs = Date.now() - transitionStartedAt;

    // Admit the same deferred-write interval after the warm transition too.
    await page.waitForTimeout(1_700);
    await expectBodyRequestsDrained();
    const origins = [...new Set(requests.map(request => request.origin))];
    expect(origins).toHaveLength(1);

    const transition = requests.slice(measuredAt);
    const bodyRequests = transition.filter(isBodyRequest);
    const surfaceResolutionRequests = transition.filter(request => (
      request.method === "POST" && request.pathname === "/__cad/surfaces"
    ));
    const counts = Object.fromEntries([...new Set(transition.map(request => request.pathname))]
      .map(pathname => [pathname, transition.filter(request => request.pathname === pathname).length]));
    const displayedComponents = await page.evaluate(() => window.__cadDisplayRecords?.().length || 0);
    console.info(`[CAD tab reopen] ${JSON.stringify({ componentCount: MANY_COMPONENT_COUNT,
      displayedComponents, switchElapsedMs, observedElapsedMs: Date.now() - transitionStartedAt,
      origins, counts, transition, bodyRequests, surfaceResolutionRequests })}`);
    expect(bodyRequests).toEqual([]);
    expect(surfaceResolutionRequests).toEqual([]);
    expect(displayedComponents).toBe(MANY_COMPONENT_COUNT);
    expect(errors).toEqual([]);
  } finally {
    page.off("request", recordRequest);
    page.off("requestfinished", finishRequest);
    page.off("requestfailed", finishRequest);
  }
});

test("STEP features run in the packaged worker, and switching files reuses their recognition", async () => {
  await selectOrOpenFile("part.step");
  await expectCadReady("part.step");
  const model = page.getByRole("list", { name: "Model", exact: true });
  // A lone part is presented as its features: there is no part row to expand.
  await expect(model.getByRole("button", { name: "Expand part.step", exact: true })).toHaveCount(0);
  const feature = model.getByRole("button", { name: /^Select Base (extrude|revolve)$/ }).first();
  await expect(feature).toBeVisible();
  // The packaged worker ran (under the desktop CSP), whenever this file was first shown.
  const recognized = recognitionWorkers;
  expect(recognized).toBeGreaterThan(0);

  await selectOrOpenFile("hinge.urdf");
  await selectOrOpenFile("part.step");
  await expectCadReady("part.step");
  await expect(feature).toBeVisible();
  await feature.click();
  await expect(feature).toHaveAttribute("aria-pressed", "true");
  expect(recognitionWorkers).toBe(recognized);
  expect(errors).toEqual([]);
  await page.keyboard.press("Escape");
  await expect(feature).toHaveAttribute("aria-pressed", "false");
});

test("prompt actions preserve the draft, native clipboard and captured selection without sending", async () => {
  test.setTimeout(150_000);
  const previousClipboard = await app.evaluate(({ clipboard }) => ({
    text: clipboard.readText(), html: clipboard.readHTML(), rtf: clipboard.readRTF(),
    image: clipboard.readImage().toDataURL(),
  }));
  try {
    const added = await page.evaluate(root => window.hardcore.projects.addPath({ path: root }), project);
    const session = await page.evaluate(projectId => window.hardcore.sessions.create({
      projectId, agentId: "claude-code", gitMode: "none",
    }), added.id);
    await page.locator(`[data-session-row="${session.id}"]`).getByRole("button").first().click();
    const draft = page.getByPlaceholder("Do anything");
    await draft.fill("Keep this draft intact.");
    await selectOrOpenFile("part.step");
    await expectCadReady("part.step");
    const model = page.getByRole("list", { name: "Model", exact: true });
    // Copy Reference, from a feature row's menu (the viewport's menu over its faces), is what
    // writes the native clipboard; nothing after it here may.
    const feature = model.getByRole("button", { name: /^Select Base (extrude|revolve)$/ }).first();
    await feature.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Copy Reference", exact: true }).click();
    const copiedReference = await app.evaluate(({ clipboard }) => clipboard.readText());
    // The ordinary CAD copy grammar: a selector copies bare (the file is the one it is pasted
    // about); only the whole file names its path, as `part.step#`.
    expect(copiedReference).toMatch(/^#o1\.f\d+(,o1\.f\d+)*$/);
    const chips = page.locator("[data-composer] [data-reference-chip]");
    await expect(chips).toHaveCount(0);
    await expect(draft).toHaveText("Keep this draft intact.");

    // This single-component import exposes its model root as a whole-resource selection,
    // made in the viewport under Parts. Exercise that identity explicitly rather than assuming o1.
    const details = page.getByRole("region", { name: "Reference details", exact: true });
    await selectWholePart();
    await expect(page.locator("[data-reference-tip]")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(details).toHaveCount(0);
    await selectWholePart();

    await page.getByRole("button", { name: "Add to prompt", exact: true }).click();
    await expect(chips).toHaveCount(1);
    await expect(chips).toHaveAttribute("data-file", "part.step");
    const selector = await chips.getAttribute("data-selector");
    // The prompt serializer renders the whole-resource identity as the bare file.
    expect(selector).toBe("");
    await expect(draft).toContainText("Keep this draft intact.");
    await expect(draft).toBeFocused();
    expect(await app.evaluate(({ clipboard }) => clipboard.readText())).toBe(copiedReference);

    await page.getByRole("button", { name: "Take snapshot", exact: true }).click();
    await expect(page.locator("[data-composer]").getByText("part-view.png", { exact: true })).toHaveCount(1);
    await expect(chips).toHaveCount(1);
    await expect(chips).toHaveAttribute("data-selector", selector!);
    await expect(draft).toContainText("Keep this draft intact.");
    await expect(draft).toBeFocused();
    const unsent = await page.evaluate(id => window.hardcore.sessions.state({ id }), session.id);
    expect(unsent?.state.turns).toHaveLength(0);
    expect(errors).toEqual([]);
  } finally {
    await app.evaluate(({ clipboard, nativeImage }, previous) => {
      const image = nativeImage.createFromDataURL(previous.image);
      clipboard.write({ text: previous.text, html: previous.html, rtf: previous.rtf,
        ...(!image.isEmpty() ? { image } : {}) });
    }, previousClipboard);
  }
});
