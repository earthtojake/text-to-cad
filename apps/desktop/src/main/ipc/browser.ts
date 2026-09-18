import { BrowserWindow } from "electron";
import { browserService } from "../browser/service";
import type { browserIpc } from "../../shared/ipc/browser";
import type { IpcHandlers } from "../../shared/ipc/define";
import type { BrowserTarget } from "../../shared/browser";
import { rootOf } from "./explorer";
import { IpcError, type IpcContext } from "./register";
const scope = (request: { projectId: string; root?: string | null }) => ({ projectId: request.projectId, root: rootOf(request.projectId, request.root) });
export const browserHandlers = {
  browser: {
    ensure: request => browserService.open(scope(request), request),
    metadata: request => browserService.metadata(scope(request), request.tabId),
    navigate: async request => await browserService.invoke("navigate", scope(request), request) as BrowserTarget,
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
