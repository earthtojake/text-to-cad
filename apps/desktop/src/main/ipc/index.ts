/**
 * Every IPC handler the app serves, assembled into the shape of the contract.
 *
 * P0 covers projects, sessions (read-only), settings, shell and app info.
 * Later phases add branches next to these: `agents.*` and `acp.*` (P1),
 * `explorer.*` (P3), `cad.*` (P4/P5), `git.*` (P7). Each one is a new branch
 * in `src/shared/ipc.ts` and a new object here — `registerIpc` refuses to
 * start if the two disagree.
 */
import { BrowserWindow, app, dialog, shell } from "electron";

import {
  ipcContract,
  type IpcContract,
  type IpcEventChannel,
  type IpcEventPayload,
} from "../../shared/ipc";
import { projects, sessions, settings } from "../db/repositories";
import { track } from "../telemetry";
import { appHandlers } from "./app";
import { IpcError, emit, registerIpc, type IpcContext } from "./register";

/** Broadcast to every open window. */
export function broadcast<C extends IpcEventChannel>(channel: C, payload: IpcEventPayload<C>) {
  emit(
    BrowserWindow.getAllWindows().map((window) => window.webContents),
    channel,
    payload,
  );
}

const handlers = {
  app: {
    info: () => ({
      // Stamped from the repository's VERSION by electron.vite.config.ts in
      // development; in a packaged app both it and app.getVersion() come from
      // the same electron-builder metadata.
      version: app.isPackaged ? app.getVersion() : __APP_VERSION__,
      platform: process.platform as "darwin" | "win32" | "linux",
      isDev: !app.isPackaged,
    }),
    ...appHandlers,
  },

  projects: {
    list: () => projects.list(),

    add: async (_request: void, ctx: IpcContext) => {
      const window = BrowserWindow.fromWebContents(ctx.sender);
      const result = window
        ? await dialog.showOpenDialog(window, openProjectDialog)
        : await dialog.showOpenDialog(openProjectDialog);
      const directory = result.canceled ? undefined : result.filePaths[0];
      if (!directory) {
        return null;
      }
      const project = projects.add(directory);
      broadcast("projects.changed", projects.list());
      return project;
    },

    addPath: ({ path: directory }: { path: string }) => {
      const project = projects.add(directory);
      broadcast("projects.changed", projects.list());
      return project;
    },

    remove: ({ id }: { id: string }) => {
      projects.remove(id);
      broadcast("projects.changed", projects.list());
      broadcast("sessions.changed", sessions.list());
    },

    rename: ({ id, name }: { id: string; name: string }) => {
      const project = projects.rename(id, name);
      broadcast("projects.changed", projects.list());
      return project;
    },
  },

  sessions: {
    list: ({ projectId }: { projectId?: string }) => sessions.list(projectId),
  },

  settings: {
    get: () => settings.get(),
    set: (patch: Parameters<typeof settings.set>[0]) => {
      const next = settings.set(patch);
      broadcast("settings.changed", next);
      // The field's NAME, never its value: "someone changed the git mode" is a
      // product question, "to what" is their business (src/main/telemetry.ts).
      for (const key of Object.keys(patch) as (keyof typeof patch & string)[]) {
        track({ name: "settings_changed", key });
      }
      return next;
    },
  },

  window: {
    state: () => settings.windowState(),
  },

  shell: {
    openExternal: async ({ url }: { url: string }) => {
      // `z.string().url()` accepts `file:` and every custom scheme the OS has
      // a handler for. The renderer may not hand the operating system one of
      // those, so the allowed schemes are named here rather than inferred.
      const { protocol } = new URL(url);
      if (protocol !== "http:" && protocol !== "https:") {
        throw new IpcError(`refusing to open a ${protocol} URL`);
      }
      await shell.openExternal(url);
    },

    showItemInFolder: ({ path: target }: { path: string }) => {
      shell.showItemInFolder(target);
    },
  },
} satisfies Parameters<typeof registerIpc<IpcContract>>[1];

const openProjectDialog = {
  title: "Add project",
  buttonLabel: "Add project",
  properties: ["openDirectory", "createDirectory"],
} as const satisfies Electron.OpenDialogOptions;

export function registerIpcHandlers() {
  registerIpc(ipcContract, handlers);
}
