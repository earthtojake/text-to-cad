/**
 * `dialogs.*` handlers: the native choosers, parented to the window that asked
 * so they arrive as sheets on macOS rather than as free-floating panels.
 */
import { BrowserWindow, dialog } from "electron";

import type { IpcHandlers } from "../../shared/ipc";
import type { dialogsContract } from "../../shared/ipc/dialogs";
import type { IpcContext } from "./register";

async function choose(
  ctx: IpcContext,
  options: Electron.OpenDialogOptions,
): Promise<{ path: string } | null> {
  const window = BrowserWindow.fromWebContents(ctx.sender);
  const result = window
    ? await dialog.showOpenDialog(window, options)
    : await dialog.showOpenDialog(options);
  const chosen = result.canceled ? undefined : result.filePaths[0];
  return chosen ? { path: chosen } : null;
}

export const dialogsHandlers = {
  dialogs: {
    chooseDirectory: (request, ctx) =>
      choose(ctx, {
        title: request.title ?? "Choose a folder",
        defaultPath: request.defaultPath,
        buttonLabel: "Choose",
        properties: ["openDirectory", "createDirectory"],
      }),

    chooseFile: (request, ctx) =>
      choose(ctx, {
        title: request.title ?? "Choose a file",
        defaultPath: request.defaultPath,
        buttonLabel: "Choose",
        filters: request.filters,
        properties: ["openFile"],
      }),
  },
} satisfies IpcHandlers<typeof dialogsContract, IpcContext>;
