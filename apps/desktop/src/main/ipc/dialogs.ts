/**
 * `dialogs.*` handlers: the native choosers, parented to the window that asked
 * so they arrive as sheets on macOS rather than as free-floating panels.
 */
import { stat } from "node:fs/promises";

import { BrowserWindow, dialog } from "electron";

import type { IpcHandlers } from "../../shared/ipc";
import type { dialogsContract } from "../../shared/ipc/dialogs";
import type { IpcContext } from "./register";

/**
 * A chooser's starting folder, or nothing when it is gone. A remembered folder
 * (Settings › default project folder, worktree root) can be moved or deleted
 * after it was chosen; handing the OS a path that does not exist opens the
 * sheet somewhere arbitrary instead of where it would have opened unasked.
 * `directory` asks for a folder, as `projects.add` does: a default that is now
 * a file is left off a folder chooser, and stays valid for the file chooser.
 */
export async function existingPath(
  path: string | undefined,
  { directory = false }: { directory?: boolean } = {},
): Promise<string | undefined> {
  if (!path) {
    return undefined;
  }
  try {
    const found = await stat(path);
    return !directory || found.isDirectory() ? path : undefined;
  } catch {
    return undefined;
  }
}

async function choose(
  ctx: IpcContext,
  options: Electron.OpenDialogOptions,
): Promise<{ path: string } | null> {
  const window = BrowserWindow.fromWebContents(ctx.sender);
  const directory = options.properties?.includes("openDirectory") ?? false;
  const asked = { ...options, defaultPath: await existingPath(options.defaultPath, { directory }) };
  const result = window
    ? await dialog.showOpenDialog(window, asked)
    : await dialog.showOpenDialog(asked);
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
