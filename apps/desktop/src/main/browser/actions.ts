import fs from "node:fs/promises";
import type { ActionDeps, RendererCommands } from "../integrations/actions";
import type { BridgeActions, BridgeSession } from "../integrations/mcp-bridge";
import { toolByName } from "../integrations/registry.mjs";
import type { BrowserMethod } from "../../shared/browser";
import { browserService, browserURL, type BrowserService } from "./service";

/** The authenticated browser domain; renderer presentation and native readiness both finish before open returns. */
export function createBrowserActions(deps: Pick<ActionDeps, "sessionRoot">, commands: Pick<RendererCommands, "request">, service: Pick<BrowserService, "open" | "invoke" | "list"> = browserService): BridgeActions {
  const workspace = async (session: BridgeSession, signal?: AbortSignal) => {
    signal?.throwIfAborted();
    const selected = deps.sessionRoot(session);
    if (!selected) throw new Error("This session's workspace is no longer open.");
    const root = await fs.realpath(selected.directory);
    signal?.throwIfAborted();
    return { selected, scope: { projectId: session.projectId, root } };
  };
  const actions: BridgeActions = {
    open_url: async (session, raw, signal) => {
      const params = toolByName("open_url")!.tool.inputSchema.parse(raw) as { url: string };
      const url = browserURL(params.url);
      const { selected, scope } = await workspace(session, signal);
      const opened = await commands.request({ kind: "open-url", projectId: session.projectId,
        root: selected.root, rootDirectory: selected.directory, url }, signal) as { tabId: string };
      signal?.throwIfAborted();
      const target = await service.open(scope, { tabId: opened.tabId, url });
      signal?.throwIfAborted();
      return { ...target, opened: target.url };
    },
  };
  const methods: Record<string, BrowserMethod> = { browser_state: "state", browser_screenshot: "screenshot", browser_navigate: "navigate", browser_input: "input" };
  for (const [name, method] of Object.entries(methods)) actions[name] = async (session, raw, signal) => {
    const params = toolByName(name)!.tool.inputSchema.parse(raw) as Record<string, unknown>;
    const { selected, scope } = await workspace(session, signal);
    // A restored inactive strip tab has no native page until its first use.
    if (!service.list(scope).some(tab => tab.tabId === params.tabId)) {
      const tab = await commands.request({ kind: "tab-resource", projectId: session.projectId,
        root: selected.root, rootDirectory: selected.directory, tabId: String(params.tabId) }, signal) as { kind: string; url?: string | null };
      if (tab.kind !== "browser") throw new Error("This tab is not a browser page.");
      signal?.throwIfAborted();
      await service.open(scope, { tabId: String(params.tabId), url: tab.url });
    }
    signal?.throwIfAborted();
    const result = await service.invoke(method, scope, method === "input" ? { tabId: params.tabId, input: params.action } : params);
    if (method === "screenshot") {
      const image = result as { data: string; mimeType: string; tabId: string };
      return { tabId: image.tabId, mimeType: image.mimeType, base64: image.data };
    }
    return result;
  };
  return actions;
}
