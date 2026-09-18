import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import type { ActionDeps, RendererCommands } from "../integrations/actions";
import type { BridgeSession } from "../integrations/mcp-bridge";
import { browserService, type BrowserService } from "./service";
import { ScopedBrowserCdp } from "./cdp";

/** Session lifetime and renderer-owned tabs are the only app-specific pieces. */
export class BrowserConnections {
  private readonly entries = new Map<string, Promise<ScopedBrowserCdp>>();
  constructor(private readonly deps: Pick<ActionDeps, "sessionRoot">, private readonly commands: Pick<RendererCommands, "request">,
    private readonly artifacts: string, private readonly service: BrowserService = browserService) {}
  async connect(session: BridgeSession, signal?: AbortSignal) {
    signal?.throwIfAborted();
    const workspace = this.deps.sessionRoot(session);
    if (!workspace) throw new Error("This session's workspace is no longer open.");
    const root = await fs.realpath(workspace.directory);
    signal?.throwIfAborted();
    let pending = this.entries.get(session.sessionId);
    if (!pending) {
      pending = (async () => {
        const scope = { projectId: session.projectId, root };
        const command = (kind: "open-url" | "show-tab" | "close-tab", extra: { tabId?: string; url?: string }, signal: AbortSignal) => this.commands.request({
          kind, projectId: session.projectId, root: workspace.root, rootDirectory: root, ...extra,
        }, signal);
        const endpoint = new ScopedBrowserCdp(this.service, scope, {
          open: async (url, signal) => {
            const tab = await command("open-url", { url }, signal) as { tabId: string };
            signal.throwIfAborted();
            await this.service.open(scope, { tabId: tab.tabId, url });
            return tab.tabId;
          },
          show: (tabId, signal) => command("show-tab", { tabId }, signal),
          close: async (tabId, signal) => { await command("close-tab", { tabId }, signal); await this.service.invoke("close", scope, { tabId }).catch(() => {}); },
        });
        await endpoint.start();
        return endpoint;
      })();
      this.entries.set(session.sessionId, pending);
      void pending.catch(() => { if (this.entries.get(session.sessionId) === pending) this.entries.delete(session.sessionId); });
    }
    const endpoint = await pending;
    if (this.entries.get(session.sessionId) !== pending) throw new Error("Browser session authorization changed.");
    signal?.throwIfAborted();
    const outputDir = path.join(this.artifacts, createHash("sha256").update(session.sessionId).digest("hex"));
    await fs.mkdir(outputDir, { recursive: true });
    return { endpoint: await endpoint.start(), root, outputDir };
  }
  revoke(sessionId: string) {
    const pending = this.entries.get(sessionId); this.entries.delete(sessionId);
    void pending?.then(endpoint => endpoint.dispose()).catch(() => {});
  }
  async dispose() {
    const pending = [...this.entries.values()]; this.entries.clear();
    await Promise.allSettled(pending.map(async entry => (await entry).dispose()));
  }
}
