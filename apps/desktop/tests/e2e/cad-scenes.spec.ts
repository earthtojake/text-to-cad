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
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: "File", exact: false }).click();
  await page.getByLabel("Filter files").fill(file);
  await page.getByRole("option", { name: file, exact: false }).first().click();
  await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible({ timeout: 90_000 });
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

async function setDisplayMode(mode: string) {
  await page.getByRole("tab", { name: "Display", exact: true }).click();
  const value = page.getByRole("tabpanel", { name: "Display", exact: true }).getByRole("combobox", { name: "Mode" });
  await value.click();
  await page.getByRole("option", { name: mode, exact: true }).click();
  await expect(value).toContainText(mode);
  // Retain the helper's original return to geometry inspection.
  const model = page.getByRole("tab", { name: "Model", exact: true });
  if (await model.count()) await model.click();
  // The file-session writer batches ordinary UI changes for 180ms.
  await page.waitForTimeout(250);
}

async function expectDisplayMode(mode: string) {
  await page.getByRole("tab", { name: "Display", exact: true }).click();
  await expect(page.getByRole("tabpanel", { name: "Display", exact: true })
    .getByRole("combobox", { name: "Mode" })).toContainText(mode);
  const model = page.getByRole("tab", { name: "Model", exact: true });
  if (await model.count()) await model.click();
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
  await expect(page.locator("[data-file-status] .animate-spin")).toHaveCount(0);
  await expect(page.getByRole("status").filter({
    hasText: /Recognizing geometry|Loading model geometry/,
  })).toHaveCount(0);
  const model = page.getByRole("list", { name: "Model", exact: true });
  await expect(model).toBeVisible({ timeout: 15_000 });
  if (componentCount === 1) {
    await expect(page.getByRole("tabpanel", { name: "Model", exact: true })
      .getByText("1 feature", { exact: true })).toBeVisible({ timeout: 15_000 });
  }
}

test("View presets preserve authored materials and independent tools without a Materials editor", async () => {
  test.setTimeout(150_000);
  await openFile("part.step");
  await expect(page.getByRole("list", { name: "Model", exact: true })).toBeVisible({ timeout: 90_000 });
  await page.getByRole("list", { name: "Model", exact: true })
    .getByRole("button", { name: "Select part.step", exact: true }).click();
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
  const viewTab = page.getByRole("tab", { name: "Display", exact: true });
  const view = page.getByRole("tabpanel", { name: "Display", exact: true });
  const mode = view.getByRole("combobox", { name: "Mode" });
  await viewTab.click();
  const displaySettings = view.getByRole("button", { name: "Surfaces", exact: true });
  await expect(displaySettings).toHaveAttribute("aria-expanded", "true");
  await expect(displaySettings.locator("svg")).toHaveCount(0);
  expect((await displaySettings.boundingBox())?.height).toBe(28);
  expect(await displaySettings.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element).fontSize)).toBe("12px");
  await expect(view.getByRole("button", { name: "View", exact: true })).toHaveCount(0);
  await expect(view.getByRole("combobox", { name: "Projection", exact: true })).toBeVisible();
  const restingBackground = await displaySettings.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element.parentElement!.parentElement!).backgroundColor);
  await displaySettings.hover();
  await expect.poll(() => displaySettings.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element).textDecorationLine)).not.toContain("underline");
  await expect.poll(() => displaySettings.evaluate(element => element.ownerDocument.defaultView!.getComputedStyle(element.parentElement!.parentElement!).backgroundColor)).not.toBe(restingBackground);
  await view.getByRole("button", { name: "Clip", exact: true }).click();
  await expect(view.getByLabel("Clip X position", { exact: true })).toBeVisible();
  await expect(view.getByLabel("Amount value", { exact: true })).toBeVisible();
  await mode.click();
  await page.getByRole("option", { name: "Wireframe", exact: true }).click();
  await expect(mode).toContainText("Wireframe");
  await expect(page.getByRole("tab", { name: "Materials", exact: true })).toHaveCount(0);

  await mode.click();
  await page.getByRole("option", { name: "Render", exact: true }).click();
  await expect(viewTab).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("button", { name: "Theme settings", exact: true })).toHaveCount(0);
  const renderingSettings = view.getByRole("button", { name: "Lighting", exact: true });
  await expect(renderingSettings).toHaveAttribute("aria-expanded", "true");
  const exposure = view.getByLabel("Exposure value", { exact: true });
  await expect(view.getByRole("combobox", { name: "Quality", exact: true })).toContainText("Preview");
  await exposure.fill("1.5");
  await exposure.press("Enter");
  await expect(mode).toContainText("Custom");
  await view.getByRole("button", { name: "Disable Lighting", exact: true }).click();
  await expect(exposure).toHaveCount(0);
  await expect(mode).toBeVisible();
  await renderingSettings.click();
  await expect(exposure).toHaveValue("0.0 EV");
  await exposure.fill("1.5");
  await exposure.press("Enter");
  await expect(page.getByRole("tab", { name: "Materials", exact: true })).toHaveCount(0);
  await expect(page.locator("[data-cad-materials-settings-section]")).toHaveCount(0);
  await expect(page.locator("[data-file-panel-container]")).toHaveCount(1);
  await page.screenshot({ path: test.info().outputPath("render-view.png"), animations: "disabled" });

  await mode.click();
  await page.getByRole("option", { name: "Wireframe", exact: true }).click();
  await expect(viewTab).toHaveAttribute("aria-selected", "true");
  await expect(renderingSettings).toHaveAttribute("aria-expanded", "false");
  await expect(exposure).toHaveCount(0);
  await expect(view.getByLabel("Clip X position", { exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Studio", exact: true })).toHaveCount(0);
  await mode.click();
  await page.getByRole("option", { name: "Render", exact: true }).click();
  await expect(exposure).toHaveValue("0.0 EV");
  await mode.click();
  await page.getByRole("option", { name: "Solid", exact: true }).click();
  await page.getByRole("tab", { name: "Model", exact: true }).click();
  await page.getByRole("list", { name: "Model", exact: true })
    .getByRole("button", { name: "Select part.step", exact: true }).click();
  await expect(materialInfo).toContainText("Brushed steel");
  const sidecarPath = path.join(project, "part.step.json");
  const sidecar = JSON.parse(fs.readFileSync(sidecarPath, "utf8"));
  delete sidecar.appearance;
  fs.writeFileSync(sidecarPath, JSON.stringify(sidecar));
  await expect(materialInfo).toContainText("Unassigned", { timeout: 30_000 });
  expect(await page.evaluate(() => localStorage.getItem("cad-viewer:theme"))).toBeNull();
  expect(errors).toEqual([]);
});

test("robot Motion edits, preserves and resets a joint through the desktop Inspector", async () => {
  await openFile("hinge.urdf");
  await page.getByRole("tab", { name: "Kinematics", exact: true }).click();
  await expect(page.getByRole("tabpanel", { name: "Kinematics", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Joints", exact: true })).toHaveCount(0);
  const joint = page.getByLabel("hinge value in deg", { exact: true });
  await expect(joint).toHaveValue("0°");
  await joint.fill("35");
  await joint.press("Enter");
  await expect(joint).toHaveValue("35°");
  await page.getByRole("button", { name: "Show files", exact: true }).click();
  await expect(joint).toBeHidden();
  await page.locator("header [data-file-panel=cad-file-sheet]").click();
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
  await page.getByRole("tab", { name: "Kinematics", exact: true }).click();
  const animation = page.getByRole("tabpanel", { name: "Kinematics", exact: true });
  const play = animation.getByRole("button", { name: "Play animation", exact: true });
  // The data: module regression renders an error in this panel instead of controls.
  await expect(play).toBeEnabled();
  const time = animation.getByLabel("Animation time value", { exact: true });
  await expect(time).toHaveValue("0.00s");

  await expect.poll(async () => page.evaluate(() => window.__cadDisplayRecords?.().length || 0)).toBeGreaterThan(0);
  const rest = await page.evaluate(() => window.__cadDisplayRecords?.()[0]);
  expect(rest?.matrix).toHaveLength(16);
  if (!rest?.matrix) throw new Error("Animated STEP did not publish a display transform");
  const restX = rest.matrix[12]!;
  const displayMatrix = () => page.evaluate(partId => (
    window.__cadDisplayRecords?.().find(record => record.partId === partId)?.matrix || null
  ), rest.partId);

  await play.click();
  await expect.poll(async () => Number.parseFloat(await time.inputValue())).toBeGreaterThan(0.05);
  await expect.poll(async () => (await displayMatrix())?.[12] ?? restX).toBeGreaterThan(restX + 0.05);
  await animation.getByRole("button", { name: "Pause animation", exact: true }).click();
  await expect(play).toBeVisible();

  await time.fill("1.25");
  await time.press("Enter");
  await expect(time).toHaveValue("1.25s");
  // Read the existing diagnostic seam's live mesh matrix, not just transport state.
  await expect.poll(async () => (await displayMatrix())?.[12] ?? restX).toBeCloseTo(restX + 1.25, 6);
  await page.screenshot({ path: test.info().outputPath("embedded-step-animation.png"), animations: "disabled" });
  await animation.getByRole("button", { name: "Restart animation", exact: true }).click();
  await expect(time).toHaveValue("0.00s");
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
    // These documents have the same STEP bytes but distinct per-file state.
    // Warm both before measuring the A -> B -> A reopen path.
    await selectOrOpenFile("many-a.step");
    await expectCadReady("many-a.step", MANY_COMPONENT_COUNT);
    await setDisplayMode("Wire");
    await expectCadReady("many-a.step", MANY_COMPONENT_COUNT);
    await selectOrOpenFile("many-b.step");
    await expectCadReady("many-b.step", MANY_COMPONENT_COUNT);
    await setDisplayMode("Flat");
    await expectCadReady("many-b.step", MANY_COMPONENT_COUNT);
    await selectOrOpenFile("many-a.step");
    await expectCadReady("many-a.step", MANY_COMPONENT_COUNT);
    await expectDisplayMode("Wire");
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
    await expectDisplayMode("Flat");
    await expect(page.locator("[data-cad-surface]")).toHaveCount(1);
    await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible();
    await selectOrOpenFile("many-a.step");
    await expectCadReady("many-a.step", MANY_COMPONENT_COUNT);
    await expectDisplayMode("Wire");
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

test("STEP feature expansion runs the packaged worker once and reuses recognition after switching files", async () => {
  let recognitionWorkers = 0;
  const countWorker = (worker: { url(): string }) => {
    if (worker.url().includes("modelingTree.worker")) recognitionWorkers += 1;
  };
  page.on("worker", countWorker);
  try {
    await selectOrOpenFile("part.step");
    await expectCadReady("part.step");
    const model = page.getByRole("list", { name: "Model", exact: true });
    const expand = model.getByRole("button", { name: "Expand part.step", exact: true });
    await expand.click();
    const feature = model.getByRole("button", { name: /^Select Base (extrude|revolve)$/ }).first();
    await expect(feature).toBeVisible();
    expect(recognitionWorkers).toBe(1);

    await selectOrOpenFile("hinge.urdf");
    await selectOrOpenFile("part.step");
    await expectCadReady("part.step");
    if (await expand.isVisible()) await expand.click();
    await expect(feature).toBeVisible();
    await feature.click();
    await expect(feature).toHaveAttribute("aria-pressed", "true");
    expect(recognitionWorkers).toBe(1);
    expect(errors).toEqual([]);
    await page.keyboard.press("Escape");
    await model.getByRole("button", { name: "Collapse part.step", exact: true }).click();
  } finally {
    page.off("worker", countWorker);
  }
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
    // This single-component import exposes its model root as a whole-resource
    // selection. Exercise that identity explicitly rather than assuming o1.
    const row = model.getByRole("button", { name: "Select part.step", exact: true });
    await row.click();
    await expect(page.locator("[data-reference-tip]")).toHaveCount(0);
    await page.keyboard.press("Escape");
    await expect(row).toHaveAttribute("aria-pressed", "false");
    await row.click();
    await expect(row).toHaveAttribute("aria-pressed", "true");

    await row.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Copy Reference", exact: true }).click();
    const copiedReference = await app.evaluate(({ clipboard }) => clipboard.readText());
    // Core's ordinary CAD copy grammar uses a trailing # for the whole file;
    // the prompt serializer renders the same whole-resource identity as a file.
    expect(copiedReference).toBe("part.step#");
    const chips = page.locator("[data-composer] [data-reference-chip]");
    await expect(chips).toHaveCount(0);
    await expect(draft).toHaveText("Keep this draft intact.");

    await page.getByRole("button", { name: "Add to prompt", exact: true }).click();
    await expect(chips).toHaveCount(1);
    await expect(chips).toHaveAttribute("data-file", "part.step");
    const selector = await chips.getAttribute("data-selector");
    expect(selector).toBe("");
    expect(copiedReference).toBe(`part.step#${selector}`);
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
