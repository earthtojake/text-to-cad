import fs from "node:fs";
import { createHash } from "node:crypto";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from "./cad-runtime";

declare const window: {
  hardcore: HardcoreApi;
  __cadDisplayRecords?: () => { partId: string; matrix: number[] | null }[];
};
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const repoRoot = path.resolve(appRoot, "../..");
let app: ElectronApplication;
let page: Page;
let userData: string;
let project: string;
const errors: string[] = [];

test.describe.configure({ mode: "serial" });
test.beforeAll(async () => {
  // This project owns its tiny fixtures and never reads the shared models corpus.
  project = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-cad-scenes-project-"));
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
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1600, 900));
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark", reduceMotion: true, defaultGitMode: "none", fetchBeforeCreate: false }));
  await page.evaluate(root => window.hardcore.projects.addPath({ path: root }), project);
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await page.getByRole("button", { name: "Toggle explorer", exact: true }).click();
});

test.afterAll(async () => {
  await app?.close();
  const runtimeLog = userData && path.join(userData, "cad-runtime.log");
  if (runtimeLog && fs.existsSync(runtimeLog)) fs.copyFileSync(runtimeLog, test.info().outputPath("cad-runtime.log"));
  for (const directory of [userData, project]) if (directory) fs.rmSync(directory, { recursive: true, force: true });
});

async function openFile(file: string) {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: "File", exact: false }).click();
  await page.getByLabel("Filter files").fill(file);
  await page.getByRole("option", { name: file, exact: false }).first().click();
  await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible({ timeout: 90_000 });
}

test("Inspect and Render keep separate controls and preserve display, studio and material edits", async () => {
  test.setTimeout(150_000);
  await openFile("part.step");
  await expect(page.getByRole("list", { name: "Model", exact: true })).toBeVisible({ timeout: 90_000 });
  await expect(page.getByRole("button", { name: "Theme settings", exact: true })).toHaveCount(0);
  await expect(page.locator("[data-file-panel=cad-theme], [data-file-sheet=Theme]")).toHaveCount(0);
  const displayButton = page.getByRole("button", { name: "Display", exact: true });
  await displayButton.click();
  const display = page.getByRole("dialog", { name: "Display settings" });
  await display.getByRole("combobox", { name: "Mode" }).click();
  await page.getByRole("option", { name: "Wire", exact: true }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tab", { name: "Materials", exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Viewing mode: Inspect. Switch to Render", exact: true }).click();
  await expect(displayButton).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Theme settings", exact: true })).toHaveCount(0);
  const studio = page.locator("[data-cad-render-settings-section]");
  await expect(studio).toBeVisible();
  const exposure = studio.getByLabel("Exposure value", { exact: true });
  await exposure.fill("1.5");
  await exposure.press("Enter");
  await page.getByRole("tab", { name: "Materials", exact: true }).click();
  const materials = page.locator("[data-cad-materials-settings-section]");
  await materials.getByRole("button", { name: "Select all parts", exact: true }).click();
  await materials.getByRole("button", { name: "Satin metal", exact: true }).click();
  await expect(materials.getByRole("button", { name: "Reset authored", exact: true })).toBeEnabled();
  await expect(materials).toContainText(/Selected: .* · Satin metal/);
  await expect(page.locator("[data-file-panel-container]")).toHaveCount(1);
  await page.screenshot({ path: test.info().outputPath("render-materials.png"), animations: "disabled" });

  await page.getByRole("button", { name: "Viewing mode: Render. Switch to Inspect", exact: true }).click();
  await expect(page.getByRole("list", { name: "Model", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Studio", exact: true })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Materials", exact: true })).toHaveCount(0);
  await displayButton.click();
  await expect(display.getByRole("combobox", { name: "Mode" })).toContainText("Wire");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Viewing mode: Inspect. Switch to Render", exact: true }).click();
  await page.getByRole("tab", { name: "Studio", exact: true }).click();
  await expect(exposure).toHaveValue("1.5 EV");
  await page.getByRole("tab", { name: "Materials", exact: true }).click();
  await expect(materials.getByRole("button", { name: "Reset authored", exact: true })).toBeEnabled();
  await materials.getByRole("button", { name: "Reset authored", exact: true }).click();
  await expect(materials.getByRole("button", { name: "Reset authored", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "Viewing mode: Render. Switch to Inspect", exact: true }).click();
  expect(await page.evaluate(() => localStorage.getItem("cad-viewer:theme"))).toBeNull();
  expect(errors).toEqual([]);
});

test("robot Kinematics edits, preserves and resets a joint through the desktop Inspector", async () => {
  await openFile("hinge.urdf");
  // Primitive links supply one section; a one-item tab strip stays hidden.
  await expect(page.getByRole("region", { name: "Kinematics", exact: true })).toBeVisible();
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
  await page.getByRole("tab", { name: "Animation", exact: true }).click();
  const animation = page.getByRole("tabpanel", { name: "Animation", exact: true });
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
  // Permit the document's in-memory module without enabling data:, eval or remote scripts.
  expect(scriptSources).toEqual(["'self'", "blob:"]);
  expect(errors).toEqual([]);
});
