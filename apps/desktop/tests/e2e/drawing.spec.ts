import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";

declare const window: {
  hardcore: {
    projects: { addPath(input: { path: string }): Promise<{ id: string }> };
    settings: { set(input: Record<string, unknown>): Promise<unknown> };
    explorer: { loadTabs(input: { projectId: string }): Promise<Array<{ kind: string; id: string }>> };
    sessions: {
      create(input: { projectId: string; agentId: string; gitMode: string; name: string }): Promise<{ id: string }>;
      prompt(input: { id: string; content: Array<{ type: "text"; text: string }> }): Promise<{ stopReason: string }>;
      state(input: { id: string }): Promise<{ state: { turns: Array<{ parts: Array<Record<string, unknown>> }> } } | null>;
    };
  };
};

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
let app: ElectronApplication;
let page: Page;
let base: string;
let project: string;
let projectId: string;
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

async function drawingTool(name: "open_drawing" | "save_drawing" | "list_open_tabs", args: Record<string, unknown>) {
  const outcome = await page.evaluate(({ id, text }) => window.hardcore.sessions.prompt({ id,
    content: [{ type: "text", text }] }), { id: sessionId, text: `drawing-tool ${JSON.stringify({ name, args })}` });
  expect(outcome.stopReason).toBe("end_turn");
  const state = await page.evaluate(id => window.hardcore.sessions.state({ id }), sessionId);
  const part = state?.state.turns.flatMap(turn => turn.parts).filter(part => part.type === "tool_call" && part.title === name).at(-1);
  expect(part, JSON.stringify(state)).toBeDefined();
  const result = part!.output as { isError?: boolean; content: Array<{ type: string; text?: string }> };
  return { status: part!.status, result, answer: result?.content?.[0]?.text ?? "" };
}

test("real canvas ink attaches a PNG without submitting, survives tab switches, and saves through the agent", async () => {
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
  await expect(composer).toContainText(`temporary drawing tab ${drawingId}`);
  await expect(page.locator("[data-session-row]")).toHaveCount(0);
  await expect(page.locator("[data-turn][data-role=user]")).toHaveCount(0);
  await page.screenshot({ path: test.info().outputPath("drawing-with-prompt-dark.png"), animations: "disabled" });

  // A real keyboard shortcut must use the host's native save dialog, rather
  // than Excalidraw's browser download/File System Access persistence.
  const nativeCopy = path.join(project, "native-copy.excalidraw");
  await app.evaluate(({ dialog }, filePath) => {
    dialog.showSaveDialog = async () => ({ canceled: false, filePath });
  }, nativeCopy);
  await editor.locator('label:has(input[data-testid="toolbar-selection"])').click();
  await canvas.click({ position: { x: box.width * 0.8, y: box.height * 0.6 } });
  await page.keyboard.press("ControlOrMeta+Shift+S");
  await expect.poll(() => fs.existsSync(nativeCopy)).toBe(true);
  const nativeScene = JSON.parse(fs.readFileSync(nativeCopy, "utf8"));
  expect(nativeScene).toMatchObject({ type: "excalidraw", version: 2, source: "Hardcore" });
  expect(browserDownloads).toBe(0);

  await newTab("Browser");
  const browserId = await page.locator('[data-tab][aria-selected="true"]').getAttribute("data-tab");
  sessionId = (await page.evaluate(id => window.hardcore.sessions.create({ projectId: id,
    agentId: "claude-code", gitMode: "none", name: "Drawing tools" }), projectId)).id;
  const listed = await drawingTool("list_open_tabs", {});
  expect(listed.status, listed.answer).toBe("completed");
  expect(JSON.parse(listed.answer).tabs).toContainEqual({ id: drawingId, kind: "drawing", title: "Drawing", root: null, ephemeral: true });
  const saved = await drawingTool("save_drawing", { tabId: drawingId, path: "plan.excalidraw" });
  expect(saved.status, saved.answer).toBe("completed");
  expect(saved.result.isError).toBeFalsy();
  await expect(page.locator(`[data-tab="${browserId}"]`)).toHaveAttribute("aria-selected", "true");
  const scene = JSON.parse(fs.readFileSync(path.join(project, "plan.excalidraw"), "utf8"));
  expect(scene.type).toBe("excalidraw");
  expect(nativeScene.elements).toEqual(scene.elements);
  expect(scene.elements.filter((element: { isDeleted: boolean }) => !element.isDeleted).map((element: { type: string }) => element.type).sort()).toEqual(["freedraw", "rectangle"]);
  await page.locator(`[data-tab="${drawingId}"]`).getByRole("button", { name: "Drawing", exact: true }).click();
  await expect(surface.getByRole("button", { name: "Add to prompt", exact: true })).toBeEnabled();
  const refused = await drawingTool("save_drawing", { tabId: drawingId, path: "plan.excalidraw" });
  expect(refused.status).toBe("failed");
  expect(refused.answer).toContain("already exists");
  const reopened = await drawingTool("open_drawing", { path: "plan.excalidraw", title: "Agent reloaded" });
  expect(reopened.status, reopened.answer).toBe("completed");
  await expect(page.getByRole("tab", { name: "Agent reloaded" })).toBeVisible();
  await expect(page.locator("[data-drawing-tab]").getByRole("button", { name: "Add to prompt", exact: true })).toBeEnabled();
  expect(externalRequests).toEqual([]);
  expect(rendererErrors).toEqual([]);
});

test("import opens another temporary tab, close discards it, and same-profile reload restores only persistent tabs", async () => {
  await page.getByLabel("Drawing file", { exact: true }).setInputFiles(path.join(project, "plan.excalidraw"));
  await expect(page.getByRole("tab", { name: /^plan/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Agent reloaded" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /^Drawing/ })).toBeVisible();
  const imported = page.locator("[data-drawing-tab]");
  const importedId = (await imported.getAttribute("data-drawing-tab"))!;
  await expect(imported.getByRole("button", { name: "Add to prompt", exact: true })).toBeEnabled();
  await page.evaluate(() => window.hardcore.settings.set({ theme: "light" }));
  await expect(imported.locator(".excalidraw")).not.toHaveClass(/theme--dark/);
  await page.screenshot({ path: test.info().outputPath("drawing-import-light.png"), animations: "disabled" });
  await page.getByRole("button", { name: "Close plan", exact: true }).click();
  await expect(page.getByRole("tab", { name: /^plan/ })).toHaveCount(0);
  const closed = await drawingTool("save_drawing", { tabId: importedId, path: "closed.excalidraw" });
  expect(closed.status).toBe("failed");
  expect(closed.answer).toContain("closed");
  expect(fs.existsSync(path.join(project, "closed.excalidraw"))).toBe(false);

  await expect.poll(async () => (await page.evaluate(id => window.hardcore.explorer.loadTabs({ projectId: id }), projectId))
    .map(tab => tab.kind)).toEqual(["browser"]);
  await page.reload();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await expect(page.getByRole("tab", { name: /^Drawing/ })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Agent reloaded" })).toHaveCount(0);
  await expect(page.locator("[data-drawing-tab]")).toHaveCount(0);
  await expect(page.getByRole("tab", { name: /^New tab/ })).toBeVisible();
  await newTab("Drawing");
  await expect(page.locator("[data-drawing-tab]").getByRole("button", { name: "Add to prompt", exact: true })).toBeDisabled();
  expect(fs.readdirSync(project).sort()).toEqual(["native-copy.excalidraw", "plan.excalidraw"]);
  expect(externalRequests).toEqual([]);
  expect(rendererErrors).toEqual([]);
});
