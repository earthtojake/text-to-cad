import fs from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test, type ElectronApplication, type Page } from "@playwright/test";
import type { HardcoreApi } from "../../src/shared/ipc";
declare const window: { hardcore: HardcoreApi };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
let application: ElectronApplication, page: Page, scratch: string, origin: string;
let server: http.Server;
let sessionA: string, sessionB: string;
let projectA: { id: string; path: string };

test.beforeAll(async () => {
  scratch = await fs.mkdtemp(path.join(os.tmpdir(), "hardcore-browser-app-"));
  await fs.mkdir(path.join(scratch, "project-a"));
  server = http.createServer((_request, response) => { response.setHeader("Content-Type", "text/html"); response.end('<!doctype html><title>Persistent browser</title><label>Name <input id="name"></label><p>Native page fixture</p>'); });
  await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve); });
  const address = server.address(); if (!address || typeof address === "string") throw new Error("Missing fixture port");
  origin = `http://127.0.0.1:${address.port}/`;
  application = await electron.launch({ args: [path.join(appRoot, "out/main/index.js"), `--user-data-dir=${path.join(scratch, "profile")}`], env: { ...process.env, NODE_ENV: "test", HARDCORE_E2E_HIDDEN: "1", HARDCORE_FAKE_AGENT: path.join(appRoot, "tests/fake-agent/index.mjs") } });
  page = await application.firstWindow(); await page.waitForLoadState("domcontentloaded");
  projectA = await page.evaluate(directory => window.hardcore.projects.addPath({ path: directory }), path.join(scratch, "project-a"));
  sessionA = (await page.evaluate(projectId => window.hardcore.sessions.create({ projectId, agentId: "claude-code", gitMode: "checkout" }), projectA.id)).id;
  sessionB = (await page.evaluate(projectId => window.hardcore.sessions.create({ projectId, agentId: "claude-code", gitMode: "checkout" }), projectA.id)).id;
  await page.locator(`[data-session-row="${sessionA}"]`).click();
  await expect(page.locator("[data-explorer-ready=true]")).toBeVisible();
  await page.getByRole("button", { name: "Toggle explorer" }).click();
});
test.afterAll(async () => {
  await application?.close();
  await new Promise<void>(resolve => server?.close(() => resolve()));
  if (scratch) await fs.rm(scratch, { recursive: true, force: true });
});
async function newTab(kind: "Browser" | "File") {
  await page.getByRole("button", { name: "New tab", exact: true }).click();
  await page.getByRole("menuitem", { name: kind }).click();
  await expect(page.getByRole("menu")).toHaveCount(0);
}

test("the explorer and app tool IPC share one page across tab/session switches, then close it", async () => {
  await newTab("Browser");
  await page.getByRole("textbox", { name: "Address" }).fill(origin);
  await page.getByRole("textbox", { name: "Address" }).press("Enter");
  const tabId = (await page.locator("[data-browser-target]").getAttribute("data-browser-target"))!;
  const scope = { sessionId: sessionA, projectId: projectA.id, root: null, tabId };
  await expect.poll(async () => (await page.evaluate(scope => window.hardcore.browser.metadata(scope), scope)).url).toBe(origin);
  await expect.poll(async () => (await page.evaluate(scope => window.hardcore.browser.metadata(scope), scope)).visible).toBe(true);
  const nativeId = await application.evaluate(async ({ webContents }, origin) => {
    const target = webContents.getAllWebContents().find(contents => contents.getURL() === origin)!;
    await target.executeJavaScript("document.getElementById('name').focus()");
    return target.id;
  }, origin);
  await page.evaluate(scope => window.hardcore.browser.input({ ...scope, input: { action: "type", text: "Still here" } }), scope);
  const fieldValue = () => application.evaluate(async ({ webContents }, id) => webContents.fromId(id)!.executeJavaScript("document.getElementById('name').value"), nativeId);
  await expect.poll(fieldValue).toBe("Still here");
  await newTab("File");
  await expect(page.locator("[data-browser-target]")).toHaveCount(0);
  await expect.poll(async () => (await page.evaluate(scope => window.hardcore.browser.metadata(scope), scope)).visible).toBe(false);
  await page.getByRole("tab", { name: /127\.0\.0\.1/ }).click();
  await expect.poll(fieldValue).toBe("Still here");
  await page.locator(`[data-session-row="${sessionB}"]`).click();
  await expect(page.getByRole("tab", { name: /127\.0\.0\.1/ })).toHaveCount(0);
  await expect(page.locator("[data-browser-target]")).toHaveCount(0);
  await expect.poll(async () => (await page.evaluate(scope => window.hardcore.browser.metadata(scope), scope)).visible).toBe(false);
  await expect(page.evaluate(scope => window.hardcore.browser.metadata(scope), { ...scope, sessionId: sessionB })).rejects.toThrow();
  await page.locator(`[data-session-row="${sessionA}"]`).click();
  await expect(page.locator(`[data-browser-target="${tabId}"]`)).toBeVisible();
  await expect.poll(fieldValue).toBe("Still here");
  const attached = await application.evaluate(({ BrowserWindow }, id) => {
    const host = BrowserWindow.getAllWindows()[0]!;
    const view = host.contentView.children.find(child => (child as Electron.WebContentsView).webContents?.id === id)!;
    return { visible: view.getVisible(), bounds: view.getBounds() };
  }, nativeId);
  expect(attached.visible).toBe(true); expect(attached.bounds.width).toBeGreaterThan(200); expect(attached.bounds.height).toBeGreaterThan(200);
  const composer = page.getByPlaceholder("Do anything");
  await composer.fill("Keep this draft");
  await page.getByRole("button", { name: "Add page screenshot to prompt" }).click();
  const image = page.locator('[data-composer] img[alt="browser-page.png"]').first();
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate(element => (element as unknown as { naturalWidth: number }).naturalWidth)).toBeGreaterThan(200);
  await expect(composer).toContainText("Keep this draft");
  await expect(page.locator("[data-session-row]")).toHaveCount(2);
  await expect(page.locator("[data-turn][data-role=user]")).toHaveCount(0);
  await application.evaluate(async ({ webContents }, id) => {
    await webContents.fromId(id)!.executeJavaScript("{const r=document.createRange();r.selectNodeContents(document.querySelector('p'));const s=window.getSelection();s.removeAllRanges();s.addRange(r);}");
  }, nativeId);
  await page.getByRole("button", { name: "Add selected text to prompt" }).click();
  await expect(page.locator("[data-composer]").getByText("browser-selection.txt")).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("browser-app-shell.png") });
  await page.getByRole("tab", { name: /127\.0\.0\.1/ }).getByRole("button", { name: /Close/ }).click();
  await expect.poll(() => application.evaluate(({ webContents }, id) => !!webContents.fromId(id), nativeId)).toBe(false);
});
