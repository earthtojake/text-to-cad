/**
 * Every IPC handler the app serves, assembled into the shape of the contract.
 *
 * P0 covers projects, sessions (read-only), settings, shell and app info;
 * P3 adds `explorer.*`, `terminal.*`, `git.*` and the `cad.viewerOrigin`
 * stub. Each phase's branch is one file in `src/shared/ipc/` and one object
 * spread in below — `registerIpc` refuses to start if the two disagree.
 */
import { BrowserWindow, app, dialog, shell } from "electron";

import { ipcContract, type IpcContract } from "../../shared/ipc";
import { projects, sessions, settings } from "../db/repositories";
import { track } from "../telemetry";
import { applySettingsEffects } from "../settings-effects";
import { acpHandlers } from "./acp";
import { agentsHandlers } from "./agents";
import { appHandlers } from "./app";
import { cadHandlers } from "./cad";
import { dialogsHandlers } from "./dialogs";
import { explorerHandlers, initExplorerServices } from "./explorer";
import { pluginsHandlers } from "./plugins";
import { runtimeHandlers } from "./runtime";
import { IpcError, broadcast, registerIpc, type IpcContext } from "./register";

export { broadcast } from "./register";

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

  /** P1: sessions and the live ACP connections behind them. */
  ...acpHandlers,

  /** P1: the agent registry, detection, install and login. */
  ...agentsHandlers,

  /** P6, stubbed until P5: the bundled plugin's state per agent. */
  ...pluginsHandlers,

  /** P6, stubbed until P5: the managed Python and cadgen runtime. */
  ...runtimeHandlers,

  /** P6: the native folder and file choosers Settings' path rows use. */
  ...dialogsHandlers,

  settings: {
    get: () => settings.get(),
    set: (patch: Parameters<typeof settings.set>[0]) => {
      const next = settings.set(patch);
      broadcast("settings.changed", next);
      // Three of these fields are instructions to the OS or to the window, not
      // stored values (src/main/settings-effects.ts).
      applySettingsEffects(next);
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

  // A phase's handlers live in their own file and are spread in, exactly as
  // its branch of the contract is (src/shared/ipc/index.ts).
  ...explorerHandlers,
  ...cadHandlers,
} satisfies Parameters<typeof registerIpc<IpcContract>>[1];

const openProjectDialog = {
  title: "Add project",
  buttonLabel: "Add project",
  properties: ["openDirectory", "createDirectory"],
} as const satisfies Electron.OpenDialogOptions;

export function registerIpcHandlers() {
  // The watcher and the pty manager push events, so they are handed the
  // broadcaster rather than reaching back for it.
  initExplorerServices(broadcast);
  registerIpc(ipcContract, handlers);
  // Boot is a settings change like any other: the login item, the menu-bar
  // item and the window's vibrancy have to match what is stored before the
  // first window is shown.
  applySettingsEffects(settings.get());
}
