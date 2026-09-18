import fs from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test, type ElectronApplication } from "@playwright/test";
import { build } from "esbuild";
import type { BrowserService } from "../../src/main/browser/service";
import type { BrowserTarget } from "../../src/shared/browser";

declare const browserFixture: { service: BrowserService; window: Electron.BrowserWindow };
type PageState = BrowserTarget & { document: { text: string; width: number; height: number; scrollY: number }; nodes: { backendNodeId: number; role: string; name: string; value?: string }[] };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
let scratch: string, application: ElectronApplication, origin: string;
let server: http.Server;
const scope = { sessionId: "browser-session", projectId: "project-a", root: "/work/project-a" };

test.beforeAll(async () => {
  scratch = await fs.mkdtemp(path.join(os.tmpdir(), "hardcore-browser-"));
  server = http.createServer((_request, response) => {
    response.setHeader("Content-Type", "text/html");
    response.end(`<!doctype html><html><head><title>Browser fixture</title></head><body>
      <label>Name <input id="name"></label><button onclick="document.getElementById('result').textContent=document.getElementById('name').value">Apply</button><p id="result">Waiting</p><a href="/next">Next page</a>
      <div style="height:1800px"></div><button onclick="document.getElementById('bottom-result').textContent='End clicked'">At end</button><p id="bottom-result">End waiting</p>
    </body></html>`);
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("No fixture address");
  origin = `http://127.0.0.1:${address.port}`;
  const entry = path.join(scratch, "service-app.cjs");
  await build({ entryPoints: [path.join(appRoot, "tests/fixtures/browser/service-app.ts")], outfile: entry, bundle: true, platform: "node", format: "cjs", external: ["electron"], target: "node22" });
  application = await electron.launch({ args: [entry, `--user-data-dir=${path.join(scratch, "profile")}`], env: { ...process.env, HARDCORE_E2E_HIDDEN: "1" } });
  await application.firstWindow();
});
test.afterAll(async () => {
  await application?.close();
  await new Promise<void>(resolve => server?.close(() => resolve()));
  if (scratch) await fs.rm(scratch, { recursive: true, force: true });
});

test("Browser Use controls the presented native page; form state survives hiding and root switches", async () => {
  const opened = await application.evaluate(async (_, { scope, url }) => {
    const target = await browserFixture.service.open(scope, { url, tabId: "form" });
    browserFixture.service.present(scope, target.tabId, browserFixture.window, "first", { x: 400, y: 100, width: 700, height: 600 });
    return browserFixture.service.metadata(scope, target.tabId);
  }, { scope, url: origin });
  expect(opened.visible).toBe(true);
  const read = () => application.evaluate(async (_, scope) => await browserFixture.service.invoke("state", scope, { tabId: "form" }) as PageState, scope);
  const state = await read();
  const textbox = state.nodes.find(node => node.role === "textbox" && node.name.includes("Name"));
  expect(textbox?.backendNodeId).toBeGreaterThan(0);
  await application.evaluate(async (_, { scope, node }) => {
    await browserFixture.service.invoke("input", scope, { tabId: "form", input: { action: "type", backendNodeId: node, text: "Discarded value" } });
    await browserFixture.service.invoke("input", scope, { tabId: "form", input: { action: "type", backendNodeId: node, text: "Retained value", clear: true } });
  }, { scope, node: textbox!.backendNodeId });
  expect((await read()).nodes.find(node => node.role === "textbox")?.value).toBe("Retained value");
  const applied = state.nodes.find(node => node.role === "button" && node.name === "Apply")!;
  await application.evaluate(async (_, { scope, node }) => {
    await browserFixture.service.invoke("input", scope, { tabId: "form", input: { action: "click", backendNodeId: node } });
  }, { scope, node: applied.backendNodeId });
  expect((await read()).document.text).toContain("Retained value");
  const captured = await application.evaluate(async (_, scope) => await browserFixture.service.invoke("screenshot", scope, { tabId: "form" }) as { data: string }, scope);
  expect(Buffer.from(captured.data, "base64").subarray(1, 4).toString()).toBe("PNG");
  await fs.writeFile(test.info().outputPath("browser-use-native.png"), Buffer.from(captured.data, "base64"));
  const promptCapture = await application.evaluate(async (_, { scope, url }) => {
    const view = browserFixture.window.contentView.children.find(child => (child as Electron.WebContentsView).webContents?.getURL().startsWith(url)) as Electron.WebContentsView;
    await view.webContents.executeJavaScript("{ const r=document.createRange();r.selectNodeContents(document.getElementById('result'));const s=window.getSelection();s.removeAllRanges();s.addRange(r); }");
    const metadata = browserFixture.service.metadata(scope, "form");
    const selection = await browserFixture.service.captureContext(scope, "form", { url: metadata.url, generation: metadata.generation, kind: "selection" });
    let staleRejected = false;
    try { await browserFixture.service.captureContext(scope, "form", { url: metadata.url, generation: metadata.generation + 1, kind: "screenshot" }); }
    catch { staleRejected = true; }
    return { selection, staleRejected };
  }, { scope, url: origin });
  expect(Buffer.from(promptCapture.selection.base64, "base64").toString()).toBe("Retained value");
  expect(promptCapture.staleRejected).toBe(true);


  await application.evaluate(async (_, { scope, url }) => {
    browserFixture.service.present(scope, "form", browserFixture.window, "first", null);
    const second = { sessionId: scope.sessionId, projectId: scope.projectId, root: "/work/other-root" };
    await browserFixture.service.open(second, { tabId: "other-root", url });
    browserFixture.service.present(second, "other-root", browserFixture.window, "second", { x: 400, y: 100, width: 700, height: 600 });
    browserFixture.service.present(scope, "form", browserFixture.window, "third", { x: 400, y: 100, width: 700, height: 600 });
    // A stale component unmount cannot hide the newly presented target.
    browserFixture.service.present(scope, "form", browserFixture.window, "first", null);
  }, { scope, url: origin });
  expect((await read()).nodes.find(node => node.role === "textbox")?.value).toBe("Retained value");
  expect((await read()).visible).toBe(true);
  const isolated = await application.evaluate(async (_, scope) => {
    const wrong = { ...scope, root: "/work/other-root" };
    try { await browserFixture.service.invoke("state", wrong, { tabId: "form" }); return false; }
    catch { return true; }
  }, scope);
  expect(isolated).toBe(true);
  expect(await application.evaluate((_, scope) => browserFixture.service.list(scope).map(target => target.tabId), scope)).toEqual(["form"]);
});

test("native resize, wheel scrolling, offscreen node clicks and keyboard input use page coordinates", async () => {
  await application.evaluate(async (_, { scope, url }) => {
    await browserFixture.service.open(scope, { tabId: "fidelity", url });
    browserFixture.service.present(scope, "fidelity", browserFixture.window, "fidelity", { x: 400, y: 100, width: 640, height: 480 });
  }, { scope, url: origin });
  const read = () => application.evaluate(async (_, scope) => await browserFixture.service.invoke("state", scope, { tabId: "fidelity" }) as PageState, scope);
  await expect.poll(async () => (await read()).document.width).toBe(640);
  await application.evaluate((_, scope) => browserFixture.service.present(scope, "fidelity", browserFixture.window, "fidelity", { x: 400, y: 100, width: 420, height: 380 }), scope);
  await expect.poll(async () => (await read()).document.width).toBe(420);
  const field = (await read()).nodes.find(node => node.role === "textbox")!;
  await application.evaluate(async (_, { scope, field }) => {
    await browserFixture.service.invoke("input", scope, { tabId: "fidelity", input: { action: "type", backendNodeId: field, text: "Keyboard result" } });
    await browserFixture.service.invoke("input", scope, { tabId: "fidelity", input: { action: "key", key: "Tab" } });
    await browserFixture.service.invoke("input", scope, { tabId: "fidelity", input: { action: "key", key: "Enter" } });
    await browserFixture.service.invoke("input", scope, { tabId: "fidelity", input: { action: "scroll", x: 200, y: 200, deltaY: 500 } });
  }, { scope, field: field.backendNodeId });
  await expect.poll(async () => (await read()).document.scrollY).toBeGreaterThan(100);
  expect((await read()).document.text).toContain("Keyboard result");
  const end = (await read()).nodes.find(node => node.role === "button" && node.name === "At end")!;
  await application.evaluate(async (_, { scope, end }) => {
    await browserFixture.service.invoke("input", scope, { tabId: "fidelity", input: { action: "click", backendNodeId: end } });
  }, { scope, end: end.backendNodeId });
  await expect.poll(async () => (await read()).document.text).toContain("End clicked");
  await application.evaluate((_, scope) => browserFixture.service.close(scope, "fidelity"), scope);
});

test("same-directory session isolation, within-session storage sharing, scheme restrictions and disposal", async () => {
  const result = await application.evaluate(async ({ webContents }, { scope, url }) => {
    const other = { ...scope, sessionId: "other-session" };
    await browserFixture.service.open(other, { url, tabId: "project-b" });
    await browserFixture.service.open(scope, { url, tabId: "same-root" });
    const scopes = browserFixture.service.list(scope);
    const contents = webContents.getAllWebContents().filter(wc => wc.getURL().startsWith(url));
    const partitionSessions = new Set(contents.map(wc => wc.session));
    let blocked = false;
    try { await browserFixture.service.invoke("navigate", scope, { tabId: "form", url: "file:///etc/passwd" }); }
    catch { blocked = true; }
    browserFixture.service.disposeSession(scope.sessionId);
    return { scopes: scopes.map(t => t.tabId), sessions: partitionSessions.size, blocked, remainingA: browserFixture.service.list(scope).length, remainingB: browserFixture.service.list(other).length };
  }, { scope, url: origin });
  expect(result).toEqual({ scopes: ["form", "same-root"], sessions: 3, blocked: true, remainingA: 0, remainingB: 1 });
});
