import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";
import { selectFixtureSession } from "./session-fixture";

declare const window: {
  DataTransfer: new () => { items: { add(file: File): void } };
  DragEvent: new (type: string, init: Record<string, unknown>) => unknown;
  ClipboardEvent: new (type: string, init: Record<string, unknown>) => unknown;
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(input: Record<string, unknown>): Promise<unknown> };
    explorer: { loadTabs(input: { sessionId: string }): Promise<Array<{ kind: string; id: string }>> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
let app: ElectronApplication;
let page: Page;
let base: string;
let project: string;
let sessionId: string;
let drawingId: string;
const externalRequests: string[] = [];
const rendererErrors: string[] = [];
let browserDownloads = 0;

test.describe.configure({ mode: "serial" });
test.beforeAll(async () => {
  base = fs.mkdtempSync(path.join(os.tmpdir(), "hardcore-drawing-e2e-"));
  project = path.join(base, "sketch-project");
  fs.mkdirSync(project);
  app = await electron.launch({
    args: [path.join(appRoot, "out", "main", "index.js"), `--user-data-dir=${path.join(base, "profile")}`],
    env: { ...process.env, NODE_ENV: "test", HARDCORE_E2E_HIDDEN: "1", CADGEN_DAEMON: "0",
      HARDCORE_FAKE_AGENT: path.join(appRoot, "tests", "fake-agent", "index.mjs") },
  });
  page = await app.firstWindow();
  page.on("pageerror", error => rendererErrors.push(error.message));
  page.on("download", () => { browserDownloads += 1; });
  // Real editor/fonts/PNG export must work offline. Local CAD services may run.
  await page.route(/^https?:\/\//, route => {
    const hostname = new URL(route.request().url()).hostname;
    if (hostname === "localhost" || hostname === "127.0.0.1") return route.continue();
    externalRequests.push(route.request().url());
    return route.abort();
  });
  await page.waitForLoadState("domcontentloaded");
  await page.evaluate(() => window.hardcore.settings.set({ theme: "dark" }));
  sessionId = (await selectFixtureSession(page, project)).id;
  await page.getByRole("button", { name: "Toggle explorer" }).click();
});
test.afterAll(async () => {
  await app?.close();
  fs.rmSync(base, { recursive: true, force: true });
});

async function newTab(kind: "Drawing" | "Browser") {
  await page.locator('[data-tab-strip] button[aria-label="New tab"][aria-haspopup="menu"]').click();
  await page.getByRole("menuitem", { name: kind }).click();
}

test("real canvas ink attaches a PNG without submitting, survives tab switches, and stays ephemeral", async () => {
  test.setTimeout(120_000);
  await newTab("Drawing");
  const surface = page.locator("[data-drawing-tab]");
  await expect(surface.locator(".excalidraw")).toBeVisible();
  drawingId = (await surface.getAttribute("data-drawing-tab"))!;
  await expect(surface.getByRole("button", { name: "Add to prompt", exact: true })).toBeDisabled();

  const name = surface.getByRole("textbox", { name: "Drawing name" });
  await name.fill("Bracket concept");
  await name.press("Enter");
  await expect(page.locator(`[data-tab="${drawingId}"]`)).toContainText("Bracket concept");
  await expect(surface.getByText("Temporary", { exact: true })).toHaveCount(0);

  const editor = surface.locator(".hardcore-drawing-editor");
  const canvas = editor.locator("canvas.excalidraw__canvas.interactive");
  await expect(canvas).toBeVisible();
  const box = (await canvas.boundingBox())!;
  expect(box.width).toBeGreaterThan(350);
  expect(box.height).toBeGreaterThan(250);
  // The shared DrawingToolbar is the editor's only control surface; every SDK control is hidden.
  await expect(editor.locator('label:has(input[data-testid="toolbar-lock"])')).toBeHidden();
  await expect(editor.getByTestId('main-menu-trigger')).toBeHidden();
  const tools = editor.getByRole('group', { name: 'Drawing tools' });
  const pan = tools.getByRole('button', { name: 'Pan view', exact: true });
  await expect(pan).toBeVisible();
  for (const control of [pan, tools.getByRole('button', { name: 'Undo', exact: true }), tools.getByRole('button', { name: 'Color', exact: true })]) {
    const controlBox = (await control.boundingBox())!;
    expect(controlBox.y - box.y).toBeLessThan(100);
    expect(controlBox.x).toBeGreaterThanOrEqual(box.x);
    expect(controlBox.x + controlBox.width).toBeLessThanOrEqual(box.x + box.width);
  }
  await tools.getByRole('button', { name: 'Rectangle', exact: true }).click();
  const x = box.x + box.width * 0.55;
  const y = box.y + box.height * 0.45;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 90, y + 65, { steps: 12 });
  await page.mouse.up();
  // Tools are sticky: the rectangle tool is still chosen after its shape.
  await expect(tools.getByRole('button', { name: 'Rectangle', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await tools.getByRole('button', { name: 'Pen', exact: true }).click();
  await page.mouse.move(x - 40, y + 120);
  await page.mouse.down();
  await page.mouse.move(x + 20, y + 90, { steps: 8 });
  await page.mouse.move(x + 70, y + 130, { steps: 8 });
  await page.mouse.up();
  await expect(surface.getByRole("button", { name: "Add to prompt", exact: true })).toBeEnabled();

  const composer = page.getByPlaceholder("Do anything");
  const draft = "Keep this existing prompt text.";
  await composer.fill(draft);
  await surface.getByRole("button", { name: "Add to prompt", exact: true }).click();
  const png = page.locator('[data-composer] img[alt="Bracket_concept.png"]').first();
  await expect(png).toBeVisible();
  // The app's CSP correctly excludes blob URLs from fetch. Inspect decoding
  // through the actual image element, which is how the attachment is shown.
  await expect.poll(() => png.evaluate(image => {
    const decoded = image as unknown as { complete: boolean; naturalWidth: number; naturalHeight: number };
    return decoded.complete && decoded.naturalWidth > 100 && decoded.naturalHeight > 100;
  })).toBe(true);
  await expect(composer).toContainText(draft);
  await expect(composer).toContainText("Drawing: Bracket concept.");
  await expect(page.locator("[data-session-row]")).toHaveCount(1);
  await expect(page.locator("[data-turn][data-role=user]")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("drawing-with-prompt-dark.png"), animations: "disabled" });

  await expect(surface.locator('.excalidraw')).not.toHaveClass(/theme--dark/);
  await expect(surface.getByRole('button', { name: 'Open drawing file' })).toHaveCount(0);
  await expect(surface.getByRole('button', { name: 'Save drawing copy' })).toHaveCount(0);
  await expect(editor.locator('.help-icon')).toBeHidden();
  await expect(tools.getByRole('button', { name: 'Undo', exact: true })).toBeVisible();
  await expect(tools.getByRole('button', { name: 'Redo', exact: true })).toBeVisible();
  await expect(editor.locator('.default-sidebar-trigger')).toBeHidden();
  // The SDK's main menu is gone with the rest of its controls; clearing is the toolbar's.
  await expect(tools.getByRole('button', { name: 'Clear drawing', exact: true })).toBeEnabled();
  await expect(editor.getByText('Help', { exact: true })).toHaveCount(0);
  await expect(editor.getByText('Open', { exact: true })).toHaveCount(0);
  await expect(editor.getByText('Save to...', { exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');

  await app.evaluate(({ dialog }) => {
    dialog.showSaveDialog = async () => { throw new Error('Drawing attempted to open a save dialog'); };
    dialog.showOpenDialog = async () => { throw new Error('Drawing attempted to open a load dialog'); };
  });
  await editor.getByRole('group', { name: 'Drawing tools' }).getByRole('button', { name: 'Select and move drawings', exact: true }).click();
  await canvas.click({ position: { x: box.width * 0.8, y: box.height * 0.6 } });
  await page.keyboard.press('ControlOrMeta+Shift+S');
  await page.keyboard.press('ControlOrMeta+O');
  await page.keyboard.press('ControlOrMeta+Shift+E');
  await page.keyboard.press('ControlOrMeta+/');
  await page.keyboard.press('ControlOrMeta+Shift+P');
  await expect(editor.getByRole('dialog')).toHaveCount(0);
  expect(browserDownloads).toBe(0);
  expect(fs.readdirSync(project)).toEqual([]);

  // Scene files cannot silently load through a drop or paste.
  await editor.evaluate(element => {
    const file = new File([JSON.stringify({ type: 'excalidraw', version: 2, elements: [] })], 'scene.excalidraw', { type: 'application/json' });
    const data = new window.DataTransfer();
    data.items.add(file);
    element.dispatchEvent(new window.DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: data }) as Parameters<typeof element.dispatchEvent>[0]);
    element.dispatchEvent(new window.ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: data }) as Parameters<typeof element.dispatchEvent>[0]);
  });
  await expect(surface.getByRole('button', { name: 'Add to prompt', exact: true })).toBeEnabled();
  await newTab('Browser');
  await page.locator(`[data-tab="${drawingId}"]`).getByRole('button', { name: 'Bracket concept', exact: true }).click();
  await expect(surface.getByRole('button', { name: 'Add to prompt', exact: true })).toBeEnabled();
  expect(externalRequests).toEqual([]);
  expect(rendererErrors).toEqual([]);
});

test("close discards ink and same-profile reload restores only persistent tabs", async () => {
  await page.evaluate(() => window.hardcore.settings.set({ theme: 'light' }));
  const surface = page.locator('[data-drawing-tab]');
  await expect(surface.locator('.excalidraw')).not.toHaveClass(/theme--dark/);
  await page.screenshot({ path: test.info().outputPath('drawing-light.png'), animations: 'disabled' });
  await page.getByRole('button', { name: 'Close Bracket concept', exact: true }).click();
  await expect(page.getByRole('tab', { name: /^Drawing/ })).toHaveCount(0);
  await newTab('Drawing');
  await expect(page.locator('[data-drawing-tab]').getByRole('button', { name: 'Add to prompt', exact: true })).toBeDisabled();
  await expect.poll(async () => (await page.evaluate(id => window.hardcore.explorer.loadTabs({ sessionId: id }), sessionId))
    .map(tab => tab.kind)).toEqual(['browser']);
  await page.reload();
  await selectFixtureSession(page, project);
  await expect(page.getByRole('tab', { name: /^Drawing/ })).toHaveCount(0);
  await expect(page.locator('[data-drawing-tab]')).toHaveCount(0);
  await expect(page.getByRole('tab', { name: /^New tab/ })).toBeVisible();
  await newTab('Drawing');
  await expect(page.locator('[data-drawing-tab]').getByRole('button', { name: 'Add to prompt', exact: true })).toBeDisabled();
  // Exercise Excalidraw's wide layout as well as the default narrow pane.
  await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0]!.setSize(1800, 1000));
  const separator = (await page.locator('[data-separator="explorer"]').boundingBox())!;
  await page.mouse.move(separator.x + separator.width / 2, separator.y + separator.height / 2);
  await page.mouse.down(); await page.mouse.move(500, separator.y + separator.height / 2, { steps: 8 }); await page.mouse.up();
  const editor = page.locator('.hardcore-drawing-editor');
  await expect(editor.locator('.excalidraw')).not.toHaveClass(/excalidraw--mobile/);
  const canvas = (await editor.locator('canvas.excalidraw__canvas.interactive').boundingBox())!;
  const wideTools = editor.getByRole('group', { name: 'Drawing tools' });
  for (const control of [wideTools.getByRole('button', { name: 'Pan view', exact: true }), wideTools.getByRole('button', { name: 'Undo', exact: true })]) {
    const bounds = (await control.boundingBox())!;
    expect(bounds.y - canvas.y).toBeLessThan(100);
  }
  await page.screenshot({ path: test.info().outputPath('drawing-wide.png'), animations: 'disabled' });
  expect(fs.readdirSync(project)).toEqual([]);
  expect(externalRequests).toEqual([]);
  expect(rendererErrors).toEqual([]);
});
