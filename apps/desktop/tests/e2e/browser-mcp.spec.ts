import fs from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { _electron as electron, expect, test, type ElectronApplication } from "@playwright/test";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";
import { WebSocket } from "ws";
import { build } from "esbuild";
import { buildMcpServer } from "../../scripts/build-mcp.mjs";
import type { BrowserService } from "../../src/main/browser/service";
import type { BrowserConnections } from "../../src/main/browser/connections";
import type { McpBridge, BridgeSession } from "../../src/main/integrations/mcp-bridge";

declare const browserMcpFixture: { service: BrowserService; scope: { projectId: string; root: string }; other: { projectId: string; root: string };
  window: Electron.BrowserWindow; calls: { kind: string; tabId?: string }[]; connections: BrowserConnections; session: BridgeSession; bridge: McpBridge;
  mcp: { command: string; args: string[]; env: { name: string; value: string }[] } };
const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
let scratch: string, application: ElectronApplication, origin: string, server: http.Server;
let client: Client;
async function connect() {
  const mcp = await application.evaluate(() => browserMcpFixture.mcp);
  const next = new Client({ name: "hardcore-browser-test", version: "1" });
  const transport = new StdioClientTransport({ command: mcp.command, args: mcp.args, cwd: scratch,
    env: Object.fromEntries(Object.entries({ ...process.env, ...Object.fromEntries(mcp.env.map(e => [e.name, e.value])) }).filter((entry): entry is [string, string] => typeof entry[1] === "string")), stderr: "pipe" });
  let stderr = "";
  transport.stderr?.on("data", chunk => { stderr += chunk.toString(); });
  try { await next.connect(transport); } catch (error) { throw new Error(`${String(error)}: ${stderr}`, { cause: error }); }
  return next;
}
async function tool(name: string, args = {}) {
  const result = await client.callTool({ name, arguments: args });
  expect(result.isError, JSON.stringify(result)).not.toBe(true);
  return (result.content as { type: string; text?: string }[]).filter(c => c.type === "text").map(c => c.text).join("\n");
}
test.beforeAll(async () => {
  scratch = await fs.mkdtemp(path.join(os.tmpdir(), "hardcore-browser-mcp-"));
  server = http.createServer((request, response) => {
    response.setHeader("content-type", "text/html");
    if (request.url === "/frame") { response.end('<label>Frame name<input></label>'); return; }
    response.end(`<!doctype html><title>${request.url}</title><label>Name<input id="name"></label>
      <input type="file" aria-label="Upload"><button onclick="alert('Native dialog')">Dialog</button>
      <button disabled id="delayed" onclick="document.querySelector('output').textContent='Ready clicked'">Delayed</button>
      <iframe src="${origin?.replace('127.0.0.1', 'localhost')}/frame"></iframe>
      <button onclick="document.querySelector('output').textContent='Saved: '+document.querySelector('input').value">Apply</button>
      <output>Waiting</output><div id="host"></div><script>const b=document.createElement('button');b.textContent='Shadow action';b.onclick=()=>document.querySelector('output').textContent='Shadow selected';document.querySelector('#host').attachShadow({mode:'open'}).append(b);setTimeout(()=>document.querySelector('#delayed').disabled=false,500);</script>`);
  });
  await new Promise<void>(resolve => server.listen(0, "127.0.0.1", resolve));
  origin = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
  // Copy the shipping server away from checkout resolution: upstream runtime assets
  // must all be present, and no installed/system browser may be needed.
  const packed = path.join(scratch, "mcp");
  await buildMcpServer({ out: packed, version: "test" });
  const entry = path.join(scratch, "app.cjs");
  await build({ entryPoints: [path.join(appRoot, "tests/fixtures/browser/mcp-app.ts")], outfile: entry, bundle: true, platform: "node", format: "cjs", external: ["electron"], target: "node22" });
  application = await electron.launch({ args: [entry, `--user-data-dir=${path.join(scratch, "profile")}`], env: { ...process.env,
    HARDCORE_E2E_HIDDEN: "1", BROWSER_FIXTURE_ROOT: scratch, BROWSER_FIXTURE_ORIGIN: origin, BROWSER_FIXTURE_MCP: path.join(packed, "server.mjs") } });
  application.process().stderr?.on("data", chunk => { void fs.appendFile(test.info().outputPath("electron.log"), chunk).catch(() => {}); });
  await application.firstWindow();
  // The test driver's separate CDP client must not auto-dismiss the MCP's dialog.
  for (const page of application.context().pages()) page.on("dialog", () => {});
  application.context().on("page", page => page.on("dialog", () => {}));
  await expect.poll(() => application.evaluate(() => typeof browserMcpFixture)).toBe("object");
  client = await connect();
});
test.afterAll(async () => {
  await client?.close(); await application?.close();
  await new Promise<void>(resolve => server?.close(() => resolve()));
  if (scratch) await fs.rm(scratch, { recursive: true, force: true });
});

test("shipping Playwright tools operate native pages, preserve them on reconnect and enforce workspace scope", async () => {
  test.setTimeout(120_000);
  const tools = (await client.listTools()).tools.map(t => t.name);
  expect(tools).toContain("browser_snapshot"); expect(tools).toContain("browser_find"); expect(tools).toContain("browser_pdf_save");
  expect(tools).not.toContain("browser_connection"); expect(tools).not.toContain("open_url");
  const tabs = await tool("browser_tabs", { action: "list" });
  expect(tabs).toContain("/form"); expect(tabs).not.toContain("/shell"); expect(tabs).not.toContain("/other");
  await tool("browser_run_code_unsafe", { code: "async page => { await page.getByRole('textbox', {name:'Name'}).fill('Retained'); await page.getByRole('button', {name:'Apply',exact:true}).click(); }" });
  expect(await tool("browser_snapshot")).toContain("Saved: Retained");
  const shadow = await tool("browser_find", { text: "Shadow action" });
  const ref = shadow.match(/button "Shadow action" \[ref=(\w+)\]/)?.[1];
  expect(ref).toBeTruthy(); await tool("browser_click", { target: ref });
  expect(await tool("browser_snapshot")).toContain("Shadow selected");
  await fs.writeFile(path.join(scratch, "upload.txt"), "fixture upload");
  await tool("browser_run_code_unsafe", { code: `async page => {
    await page.getByRole('button', {name:'Delayed',exact:true}).click();
    await page.getByLabel('Upload').setInputFiles(${JSON.stringify(path.join(scratch, "upload.txt"))});
    await page.frameLocator('iframe').getByLabel('Frame name').fill('Frame retained');
    await page.getByRole('button', {name:'Dialog',exact:true}).click();
  }` });
  await tool("browser_handle_dialog", { accept: true });
  const afterInput = await tool("browser_snapshot");
  expect(afterInput).toContain("Frame retained"); expect(afterInput).toContain("Ready clicked");
  await tool("browser_take_screenshot", { filename: "capture.png" });
  expect((await fs.readFile(path.join(scratch, "capture.png"))).subarray(1, 4).toString()).toBe("PNG");
  await tool("browser_pdf_save", { filename: "page.pdf" });
  expect((await fs.readFile(path.join(scratch, "page.pdf"))).subarray(0, 4).toString()).toBe("%PDF");
  await tool("browser_tabs", { action: "new", url: `${origin}/new` });
  expect(await application.evaluate(() => browserMcpFixture.service.list(browserMcpFixture.scope).length)).toBe(2);
  await tool("browser_tabs", { action: "select", index: 0 });
  expect(await application.evaluate(() => browserMcpFixture.service.metadata(browserMcpFixture.scope, "form").visible)).toBe(true);
  await tool("browser_tabs", { action: "close", index: 1 });
  expect(await application.evaluate(() => browserMcpFixture.calls.map(c => c.kind))).toContain("close-tab");
  await client.close(); client = await connect();
  expect(await tool("browser_snapshot")).toContain("Retained");

  const target = await application.evaluate(async () => {
    const f = browserMcpFixture;
    const wc = f.service.contents(f.other, "other"); wc.debugger.attach("1.3");
    const { targetInfo } = await wc.debugger.sendCommand("Target.getTargetInfo");
    return { ...await f.connections.connect(f.session), forbidden: targetInfo.targetId };
  });
  const socket = new WebSocket(target.endpoint);
  await new Promise<void>((resolve, reject) => { socket.once("open", resolve); socket.once("error", reject); });
  let id = 0;
  async function cdp(method: string, params = {}) {
    const key = ++id;
    const response = new Promise<{ result?: unknown; error?: { message: string } }>(resolve => {
      const receive = (data: Buffer) => { const message = JSON.parse(data.toString()); if (message.id === key) { socket.off("message", receive); resolve(message); } };
      socket.on("message", receive);
    });
    socket.send(JSON.stringify({ id: key, method, params })); return response;
  }
  expect((await cdp("Target.attachToTarget", { targetId: target.forbidden, flatten: true })).error?.message).toContain("Unknown browser target");
  expect((await cdp("Target.createTarget", { url: "file:///etc/passwd" })).error?.message).toContain("HTTP");
  expect((await cdp("Target.createBrowserContext")).error?.message).toContain("Unsupported");
  const closed = new Promise<void>(resolve => socket.once("close", () => resolve()));
  await application.evaluate(() => browserMcpFixture.bridge.revoke(browserMcpFixture.session.sessionId)); await closed;
  expect(await application.evaluate(() => browserMcpFixture.service.list(browserMcpFixture.scope).length)).toBe(1);
  expect(await application.evaluate(() => browserMcpFixture.service.list(browserMcpFixture.other).length)).toBe(1);
});
