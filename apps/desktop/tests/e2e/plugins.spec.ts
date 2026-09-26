/**
 * The base app and its plugins (src/plugins/README.md): one build launched three ways by
 * `HARDCORE_PLUGINS` — `none` (the base app alone), `csv` (the base app plus the example plugin)
 * and unset (every plugin). `PLUGIN_SHOTS=<dir>` also writes each screen there.
 */
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { cadRegistryEnvironment, cadRuntimeReady, cadTestProfile } from "./cad-runtime";
import { selectFixtureSession } from "./session-fixture";

declare const window: { hardcore: { plugins: { list(): Promise<{ id: string; enabled: boolean }[]> }; runtime: { status(): Promise<{ state: string; cadgenVersion: string | null }> } } };

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const repoRoot = path.resolve(appRoot, "../..");
let project: string;

test.describe.configure({ mode: "serial" });
test.setTimeout(240_000);

test.beforeAll(() => {
  project = fs.mkdtempSync(path.join(os.tmpdir(), "plugins-e2e-"));
  fs.copyFileSync(path.join(repoRoot, "tests/fixtures/cad/import-smoke.step"), path.join(project, "part.step"));
  fs.writeFileSync(path.join(project, "parts.csv"), "part,material,qty,mass_g\nbracket,6061-T6,4,38.2\nhinge pin,303 stainless,8,4.1\nbase plate,6061-T6,1,212.0\n\"spacer, 5 mm\",PETG,12,0.9\n");
  fs.writeFileSync(path.join(project, "README.md"), "# Plugins fixture\n\nA part, a table and this note.\n");
});
test.afterAll(() => { fs.rmSync(project, { recursive: true, force: true }); });

async function launch(plugins: string | null): Promise<{ app: ElectronApplication; page: Page; userData: string }> {
  const userData = cadTestProfile("plugins");
  const env: Record<string, string> = { ...process.env as Record<string, string>, ...cadRegistryEnvironment(userData), NODE_ENV: "test",
    CADGEN_DAEMON: "0", CADGEN_CACHE_DIR: path.join(userData, "cad-cache"), CADGEN_DAEMON_STATE_DIR: path.join(userData, "cad-daemon") };
  if (plugins === null) delete env.HARDCORE_PLUGINS; else env.HARDCORE_PLUGINS = plugins;
  const app = await electron.launch({ args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${userData}`], env });
  const page = await app.firstWindow();
  await page.waitForLoadState("domcontentloaded");
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]?.setSize(1440, 900));
  const python = process.env.CAD_DESKTOP_PYTHON ?? null;
  await page.evaluate((python) => (window as unknown as { hardcore: { settings: { set(patch: object): Promise<unknown> } } }).hardcore.settings.set({ theme: "dark", defaultGitMode: "none", fetchBeforeCreate: false,
    ...(python ? { cadPythonOverride: python } : {}) }), python);
  await selectFixtureSession(page, project);
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  return { app, page, userData };
}

async function close({ app, userData }: { app: ElectronApplication; userData: string }) {
  await app.close();
  fs.rmSync(userData, { recursive: true, force: true });
}

async function shot(page: Page, name: string) {
  const file = test.info().outputPath(`${name}.png`);
  await page.screenshot({ path: file });
  if (process.env.PLUGIN_SHOTS) {
    fs.mkdirSync(process.env.PLUGIN_SHOTS, { recursive: true });
    fs.copyFileSync(file, path.join(process.env.PLUGIN_SHOTS, `${name}.png`));
  }
}

async function openFile(page: Page, file: string) {
  const newTab = page.getByRole("button", { name: "New tab", exact: true });
  if (!(await newTab.isVisible())) await page.getByRole("button", { name: "Toggle explorer", exact: true }).click();
  await newTab.click();
  await page.getByRole("menuitem", { name: "File", exact: false }).click();
  await page.getByLabel("Filter files").fill(file);
  await page.getByRole("option", { name: file, exact: false }).first().click();
}

async function showPluginsPage(page: Page) {
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Plugins", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Plugins", exact: true }).first()).toBeVisible();
}

test("the base app alone: chat, files and the generic viewers, and no CAD", async () => {
  const run = await launch("none");
  const { page } = run;
  try {
    expect((await page.evaluate(() => window.hardcore.plugins.list())).filter(plugin => plugin.enabled)).toEqual([]);
    // Every file is listed; the ones only a plugin could show are "Not supported".
    await openFile(page, "part.step");
    await expect(page.getByText("Not supported", { exact: true })).toBeVisible();
    await expect(page.locator("[data-cad-surface]")).toHaveCount(0);
    await page.getByLabel("Filter files").fill("");
    await shot(page, "1-base-app");
    await openFile(page, "parts.csv");
    // With the CSV plugin off, a .csv is text: the code editor shows it.
    await expect(page.locator("[data-csv-table]")).toHaveCount(0);
    await expect(page.getByText("bracket,6061-T6,4,38.2")).toBeVisible();
    await showPluginsPage(page);
    await expect(page.getByText("Base app only")).toBeVisible();
    await shot(page, "2-base-app-settings");
  } finally { await close(run); }
});

test("the base app plus the CSV example plugin", async () => {
  const run = await launch("csv");
  const { page } = run;
  try {
    expect((await page.evaluate(() => window.hardcore.plugins.list())).filter(plugin => plugin.enabled).map(plugin => plugin.id)).toEqual(["csv"]);
    await openFile(page, "parts.csv");
    const table = page.locator("[data-csv-table]");
    await expect(table).toBeVisible();
    await expect(table.getByRole("columnheader", { name: "material" })).toBeVisible();
    await expect(table.getByRole("cell", { name: "spacer, 5 mm" })).toBeVisible();
    await shot(page, "3-base-plus-csv");
    await openFile(page, "part.step");
    await expect(page.getByText("Not supported", { exact: true })).toBeVisible();
  } finally { await close(run); }
});

test("every plugin: CAD opens its model, and Settings lists what each plugin adds", async () => {
  const run = await launch(null);
  const { page } = run;
  try {
    expect((await page.evaluate(() => window.hardcore.plugins.list())).every(plugin => plugin.enabled)).toBe(true);
    await showPluginsPage(page);
    for (const name of ["CAD (cad)", "PDF (pdf)", "G-code (gcode)", "CSV (csv)"]) await expect(page.getByText(name, { exact: true })).toBeVisible();
    await expect(page.getByText("csv_state", { exact: true })).toBeVisible();
    await shot(page, "4-settings-plugins");
    await page.getByRole("button", { name: "Back to app" }).click().catch(async () => { await page.keyboard.press("Escape"); });
    const runtime = await page.evaluate(() => window.hardcore.runtime.status());
    test.skip(!cadRuntimeReady(runtime), "CAD runtime required for the STEP screen");
    await openFile(page, "part.step");
    await expect(page.locator("[data-cad-surface] canvas").first()).toBeVisible({ timeout: 180_000 });
    await expect(page.getByText("Not supported", { exact: true })).toHaveCount(0);
    await expect(page.locator("[data-cad-tool-stack]").getByRole("region", { name: /^(Features|Links)$/ })).toBeVisible({ timeout: 180_000 });
    await expect(page.getByText(/Loading geometry|Reading model|Updating model/)).toHaveCount(0, { timeout: 180_000 });
    const tree = page.getByTestId("tree-toggle");
    if ((await tree.getAttribute("aria-pressed")) === "true") await tree.click();
    await page.waitForTimeout(1500);
    await shot(page, "5-all-plugins-step");
  } finally { await close(run); }
});
