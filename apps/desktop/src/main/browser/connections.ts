import fs from "node:fs/promises";
import path from "node:path";
import type { ActionDeps, RendererCommands } from "../integrations/actions";
import type { BridgeSession } from "../integrations/mcp-bridge";
import { browserService, type BrowserService } from "./service";
import { ScopedBrowserCdp } from "./cdp";
import { browserSessionKey } from "./storage";

/** Session lifetime and renderer-owned tabs are the only app-specific pieces. */
export class BrowserConnections {
  private readonly entries = new Map<string, Promise<ScopedBrowserCdp>>();
  /**
   * The newest `disposePages` call per session. Monotonic: the bridge revokes
   * before every call, so a `revoke` that reset it would restart each call at 1
   * and let a superseded one pass the guard.
   */
  private readonly disposals = new Map<string, number>();
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
        const scope = { sessionId: session.sessionId, projectId: session.projectId, root };
        const command = (kind: "open-url" | "show-tab" | "close-tab", extra: { tabId?: string; url?: string }, signal: AbortSignal) => this.commands.request({
          kind, sessionId: session.sessionId, projectId: session.projectId, root: workspace.root, rootDirectory: root, ...extra,
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
    const outputDir = path.join(this.artifacts, browserSessionKey(session.sessionId));
    await fs.mkdir(outputDir, { recursive: true });
    return { endpoint: await endpoint.start(), root, outputDir };
  }
  revoke(sessionId: string) {
    const pending = this.entries.get(sessionId); this.entries.delete(sessionId);
    void pending?.then(endpoint => endpoint.dispose()).catch(() => {});
  }
  /**
   * A workspace change: the pages opened in a scope the session's workspace no
   * longer names go, the session stays. Pages in the scope it still names are
   * the person's explorer tabs too, and nothing tells their renderer a page went.
   */
  async disposePages(session: BridgeSession) {
    // Quick changes A to B to C can finish out of order; B's late `realpath`
    // must not keep B and close C's pages, so only the newest call acts.
    const generation = (this.disposals.get(session.sessionId) ?? 0) + 1;
    this.disposals.set(session.sessionId, generation);
    const workspace = this.deps.sessionRoot(session);
    const root = workspace ? await fs.realpath(workspace.directory).catch(() => null) : null;
    if (this.disposals.get(session.sessionId) !== generation) return;
    this.service.disposeSession(session.sessionId, root === null ? undefined : { sessionId: session.sessionId, projectId: session.projectId, root });
  }
  async dispose() {
    const pending = [...this.entries.values()]; this.entries.clear(); this.disposals.clear();
    await Promise.allSettled(pending.map(async entry => (await entry).dispose()));
  }
}
