import { app, BrowserWindow } from "electron";
import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { BrowserService } from "../../../src/main/browser/service";
import { BrowserConnections } from "../../../src/main/browser/connections";
import { McpBridge } from "../../../src/main/integrations/mcp-bridge";

app.setName("HardcoreBrowserMcpTest");
for (const flag of ["disable-background-timer-throttling", "disable-renderer-backgrounding", "disable-backgrounding-occluded-windows"])
  app.commandLine.appendSwitch(flag);
void app.whenReady().then(async () => {
  const root = fs.realpathSync(process.env.BROWSER_FIXTURE_ROOT!);
  const origin = process.env.BROWSER_FIXTURE_ORIGIN!;
  const window = new BrowserWindow({ show: false, width: 1200, height: 800 });
  await window.loadURL(`${origin}/shell`);
  const service = new BrowserService();
  const scope = { projectId: "fixture", root };
  const calls: { kind: string; tabId?: string }[] = [];
  const present = (id: string) => service.present(scope, id, window, id, { x: 0, y: 0, width: 950, height: 650 });
  const commands = { request: async (command: { kind: string; tabId?: string; url?: string }) => {
    calls.push(command);
    if (command.kind === "open-url") {
      const tab = await service.open(scope, { tabId: randomUUID(), url: command.url }); present(tab.tabId); return tab;
    }
    if (command.kind === "show-tab") { present(command.tabId!); return {}; }
    if (command.kind === "close-tab") { service.close(scope, command.tabId!); return {}; }
    throw new Error(`Unexpected command: ${command.kind}`);
  } };
  await service.open(scope, { tabId: "form", url: `${origin}/form` }); present("form");
  const other = { ...scope, root: `${root}/other` };
  await service.open(other, { tabId: "other", url: `${origin}/other` });
  const connections = new BrowserConnections({ sessionRoot: () => ({ directory: root, root: null }) }, commands, path.join(root, "artifacts"), service);
  const bridge = new McpBridge({ browser_connection: (session, _params, signal) => connections.connect(session, signal) },
    () => ({ command: process.execPath, args: [process.env.BROWSER_FIXTURE_MCP!], env: { ELECTRON_RUN_AS_NODE: "1" } }), connections);
  await bridge.start();
  const session = { sessionId: "fixture-session", projectId: scope.projectId, cwd: root };
  const mcp = bridge.serverFor(session, "browser");
  Object.assign(globalThis, { browserMcpFixture: { service, scope, other, window, calls, bridge, connections, session, mcp } });
  app.on("before-quit", () => { void bridge.stop(); service.dispose(); });
});
