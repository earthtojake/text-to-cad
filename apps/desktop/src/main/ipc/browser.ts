import fs from "node:fs";
import { BrowserWindow } from "electron";
import { browserService } from "../browser/service";
import { sweepBrowserStorage } from "../browser/storage";
import type { browserIpc } from "../../shared/ipc/browser";
import type { IpcHandlers } from "../../shared/ipc/define";
import type { BrowserTarget } from "../../shared/browser";
import { sessions } from "../db/repositories";
import { rootOf } from "./explorer";
import { IpcError, type IpcContext } from "./register";
let swept = false;
/**
 * Once, on the first renderer browser request (a restored browser tab asks at
 * launch): migrate older builds' partitions and remove those — and artifact
 * directories — whose session no longer exists. An agent's page may already
 * be open by then; `sweepBrowserStorage` skips whatever this run opened.
 */
function sweepOnce() {
  if (swept) return;
  swept = true;
  void sweepBrowserStorage(() => sessions.list()).catch((error: unknown) => console.warn(`[browser] storage sweep failed: ${String(error)}`));
}
const scope = (request: { sessionId: string; projectId: string; root?: string | null }) => {
  sweepOnce();
  const session = sessions.get(request.sessionId);
  if (!session || session.projectId !== request.projectId || session.archived) throw new IpcError("This session is no longer active.");
  // A removed worktree is a refusal the tab can show, not a raw ENOENT (and a
  // stack in main's log on every metadata poll).
  const real = (directory: string) => {
    try { return fs.realpathSync(directory); } catch { throw new IpcError("This session's workspace is missing."); }
  };
  const root = real(rootOf(request.projectId, request.root));
  if (root !== real(session.cwd)) throw new IpcError("This browser belongs to a different session workspace.");
  return { sessionId: request.sessionId, projectId: request.projectId, root };
};
/** What the tab's address bar may open; anything else is a sentence, not a generic "failed". */
const NOT_WEB_ADDRESS = "Only http and https addresses can be opened here.";
async function navigate(request: { url?: string }, resolved: ReturnType<typeof scope>) {
  if (request.url && request.url !== "about:blank") {
    let protocol = "";
    try { protocol = new URL(request.url).protocol; } catch { /* below */ }
    if (protocol !== "http:" && protocol !== "https:") throw new IpcError(NOT_WEB_ADDRESS);
  }
  try { return await browserService.invoke("navigate", resolved, request) as BrowserTarget; }
  catch (error) {
    if (error instanceof Error && error.name === "BrowserNavigationError") throw new IpcError(error.message);
    throw error;
  }
}
export const browserHandlers = {
  browser: {
    ensure: request => browserService.open(scope(request), request),
    metadata: request => browserService.metadata(scope(request), request.tabId, request.logs !== false),
    navigate: async request => await navigate(request, scope(request)),
    input: async request => await browserService.invoke("input", scope(request), request) as BrowserTarget,
    present: (request, context) => {
      const owner = BrowserWindow.fromWebContents(context.sender);
      if (!owner || owner.webContents !== context.sender) throw new IpcError("Browser views belong to an app window.");
      browserService.present(scope(request), request.tabId, owner, request.lease, request.bounds);
    },
    close: request => browserService.close(scope(request), request.tabId),
    clearConsole: request => browserService.clearConsole(scope(request), request.tabId),
    capture: request => browserService.captureContext(scope(request), request.tabId, request),
  },
} satisfies IpcHandlers<typeof browserIpc, IpcContext>;
