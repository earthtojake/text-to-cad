/**
 * `dialogs.*` handlers: the native choosers, parented to the window that asked
 * so they arrive as sheets on macOS rather than as free-floating panels.
 */
import { BrowserWindow, dialog } from "electron";
import fs from "node:fs/promises";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { parseDrawingScene } from "@hardcore/core/drawing";
import { rootOf } from "./explorer";

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
    saveDrawing: async (request, ctx) => {
      const directory = rootOf(request.projectId, request.root);
      const scene = JSON.stringify(parseDrawingScene(request.scene));
      const name = request.title.replace(/[^\p{L}\p{N}._-]/gu, "_") || "Drawing";
      const window = BrowserWindow.fromWebContents(ctx.sender);
      const options: Electron.SaveDialogOptions = {
        title: "Save drawing copy", buttonLabel: "Save copy",
        defaultPath: path.join(directory, `${name}.excalidraw`),
        filters: [{ name: "Excalidraw drawing", extensions: ["excalidraw"] }],
      };
      const result = window ? await dialog.showSaveDialog(window, options) : await dialog.showSaveDialog(options);
      if (result.canceled || !result.filePath) return null;
      // The native chooser, not the renderer, grants this exact destination.
      // Save a copy atomically; the open drawing remains temporary and unbound.
      const destination = result.filePath;
      const temporary = path.join(path.dirname(destination), `.hardcore-drawing-${randomUUID()}.tmp`);
      try {
        await fs.writeFile(temporary, scene, { flag: "wx", mode: 0o600 });
        await fs.rename(temporary, destination);
      } finally { await fs.rm(temporary, { force: true }); }
      return { path: destination };
    },
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
