import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

declare const window: {
  DataTransfer: new () => { items: { add(file: File): void } };
  DragEvent: new (type: string, init: Record<string, unknown>) => unknown;
  ClipboardEvent: new (type: string, init: Record<string, unknown>) => unknown;
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(input: Record<string, unknown>): Promise<unknown> };
    explorer: { loadTabs(input: { projectId: string }): Promise<Array<{ kind: string; id: string }>> };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
let app: ElectronApplication;
let page: Page;
let base: string;
let project: string;
let projectId: string;
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
  projectId = (await page.evaluate(root => window.hardcore.projects.addPath({ path: root }), project)).id;
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
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

  const editor = surface.locator(".hardcore-drawing-editor");
  const canvas = editor.locator("canvas.excalidraw__canvas.interactive");
  await expect(canvas).toBeVisible();
  const box = (await canvas.boundingBox())!;
  expect(box.width).toBeGreaterThan(350);
  expect(box.height).toBeGreaterThan(250);
  await editor.locator('label:has(input[data-testid="toolbar-rectangle"])').click();
  const x = box.x + box.width * 0.55;
  const y = box.y + box.height * 0.45;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + 90, y + 65, { steps: 12 });
  await page.mouse.up();
  await editor.locator('label:has(input[data-testid="toolbar-freedraw"])').click();
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
  const png = page.locator('[data-composer] img[alt="Drawing.png"]').first();
  await expect(png).toBeVisible();
  // The app's CSP correctly excludes blob URLs from fetch. Inspect decoding
  // through the actual image element, which is how the attachment is shown.
  await expect.poll(() => png.evaluate(image => {
    const decoded = image as unknown as { complete: boolean; naturalWidth: number; naturalHeight: number };
    return decoded.complete && decoded.naturalWidth > 100 && decoded.naturalHeight > 100;
  })).toBe(true);
  await expect(composer).toContainText(draft);
  await expect(composer).toContainText("Drawing: Drawing.");
  await expect(page.locator("[data-session-row]")).toHaveCount(0);
  await expect(page.locator("[data-turn][data-role=user]")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("drawing-with-prompt-dark.png"), animations: "disabled" });

  await expect(surface.locator('.excalidraw')).not.toHaveClass(/theme--dark/);
  await expect(surface.getByRole('button', { name: 'Open drawing file' })).toHaveCount(0);
  await expect(surface.getByRole('button', { name: 'Save drawing copy' })).toHaveCount(0);
  await expect(editor.locator('.help-icon')).toBeHidden();
  await expect(editor.getByRole('button', { name: 'Undo', exact: true })).toBeVisible();
  await expect(editor.getByRole('button', { name: 'Redo', exact: true })).toBeVisible();
  await expect(editor.locator('.default-sidebar-trigger')).toBeHidden();
  await editor.getByTestId('main-menu-trigger').click();
  await expect(editor.getByRole('button', { name: 'Reset the canvas', exact: true })).toBeVisible();
  await expect(editor.getByText('Help', { exact: true })).toHaveCount(0);
  await expect(editor.getByText('Open', { exact: true })).toHaveCount(0);
  await expect(editor.getByText('Save to...', { exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');

  await app.evaluate(({ dialog }) => {
    dialog.showSaveDialog = async () => { throw new Error('Drawing attempted to open a save dialog'); };
    dialog.showOpenDialog = async () => { throw new Error('Drawing attempted to open a load dialog'); };
  });
  await editor.locator('label:has(input[data-testid="toolbar-selection"])').click();
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
  await page.locator(`[data-tab="${drawingId}"]`).getByRole('button', { name: 'Drawing', exact: true }).click();
  await expect(surface.getByRole('button', { name: 'Add to prompt', exact: true })).toBeEnabled();
  expect(externalRequests).toEqual([]);
  expect(rendererErrors).toEqual([]);
});

test("close discards ink and same-profile reload restores only persistent tabs", async () => {
  await page.evaluate(() => window.hardcore.settings.set({ theme: 'light' }));
  const surface = page.locator('[data-drawing-tab]');
  await expect(surface.locator('.excalidraw')).not.toHaveClass(/theme--dark/);
  await page.screenshot({ path: test.info().outputPath('drawing-light.png'), animations: 'disabled' });
  await page.getByRole('button', { name: 'Close Drawing', exact: true }).click();
  await expect(page.getByRole('tab', { name: /^Drawing/ })).toHaveCount(0);
  await newTab('Drawing');
  await expect(page.locator('[data-drawing-tab]').getByRole('button', { name: 'Add to prompt', exact: true })).toBeDisabled();
  await expect.poll(async () => (await page.evaluate(id => window.hardcore.explorer.loadTabs({ projectId: id }), projectId))
    .map(tab => tab.kind)).toEqual(['browser']);
  await page.reload();
  await expect(page.locator('[data-explorer-ready=true]')).toBeVisible();
  await expect(page.getByRole('tab', { name: /^Drawing/ })).toHaveCount(0);
  await expect(page.locator('[data-drawing-tab]')).toHaveCount(0);
  await expect(page.getByRole('tab', { name: /^New tab/ })).toBeVisible();
  await newTab('Drawing');
  await expect(page.locator('[data-drawing-tab]').getByRole('button', { name: 'Add to prompt', exact: true })).toBeDisabled();
  expect(fs.readdirSync(project)).toEqual([]);
  expect(externalRequests).toEqual([]);
  expect(rendererErrors).toEqual([]);
});
