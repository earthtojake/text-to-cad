/**
 * Every IPC handler the app serves, assembled into the shape of the contract
 * from one handler object per contract branch: each branch is one file in
 * `src/shared/ipc/` and one handler object from `src/main/ipc/<branch>.ts`
 * spread in below, beside the few channels (`app`, `projects`, `settings`,
 * `shell`, `ui`, `window`) answered here — `registerIpc` refuses to start if
 * the two disagree.
 */
import { BrowserWindow, app, dialog, shell } from "electron";

import { ipcContract, type IpcContract } from "../../shared/ipc";
import { projects, settings } from "../db/repositories";
import { viewers } from "../cad";
import { changedSettingsKeys, track } from "../telemetry";
import { applySettingsEffects } from "../settings-effects";
import { settingsFallbacks } from "./settings-fallbacks";
import { takeQueuedCommands } from "../menu";
import { acpHandlers } from "./acp";
import { agentOptionsHandlers } from "./agent-options";
import { agentsHandlers } from "./agents";
import { appHandlers } from "./app";
import { integrationHandlers } from "./integrations";
import { cadHandlers } from "./cad";
import { clipboardHandlers } from "./clipboard";
import { browserHandlers } from "./browser";
import { dialogsHandlers, existingPath } from "./dialogs";
import { explorerHandlers, initExplorerServices, revealProjectDirectory } from "./explorer";
import { gitHandlers } from "./git";
import { refreshRuntimeAfterOverride, runtimeHandlers } from "./runtime";
import { onboardingHandlers } from "./onboarding";
import { skillsHandlers } from "./skills";
import { installE2eDoor } from "../test-door";
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
      const options = { ...openProjectDialog, ...(await defaultPathOption()) };
      const result = window
        ? await dialog.showOpenDialog(window, options)
        : await dialog.showOpenDialog(options);
      const directory = result.canceled ? undefined : result.filePaths[0];
      if (!directory) {
        return null;
      }
      const selected = projects.choose(directory);
      broadcast("ui.directorySelected", selected);
      return selected;
    },
  },

  /** P1: sessions and the live ACP connections behind them. */
  ...acpHandlers,

  /** P1: the agent registry, detection, install and login. */
  ...agentsHandlers,

  /** P2: what each agent's sessions can be configured with, between sessions. */
  ...agentOptionsHandlers,

  /** P5: the skills root every session is handed. */
  ...skillsHandlers,

  /** P5: the managed Python and cadgen runtime. */
  ...runtimeHandlers,

  /** First run: whether onboarding shows, and the sample project. */
  ...onboardingHandlers,

  /** P6: the native folder and file choosers Settings' path rows use. */
  ...dialogsHandlers,

  settings: {
    get: () => settings.get(),
    set: (patch: Parameters<typeof settings.set>[0]) => {
      const previous = settings.get();
      const next = settings.set(patch);
      broadcast("settings.changed", next);
      // Three of these fields are instructions to the OS or to the window, not
      // stored values (src/main/settings-effects.ts).
      applySettingsEffects(next);
      // A viewer is bound to the interpreter that runs it. When the override
      // changes, every viewer this app started — including the ones a project
      // open warmed before the change — is stale: stopped here, so the next
      // `cad.viewerOrigin` launches (or fails) with the interpreter that is
      // now configured, instead of handing out a process the old one runs.
      if (previous.cadPythonOverride !== next.cadPythonOverride) {
        viewers().stopAll();
        // And the status every window shows is the new interpreter's.
        void refreshRuntimeAfterOverride().catch((error: unknown) => {
          console.error("[runtime] status after the override changed:", error);
        });
      }
      // The field's NAME, never its value: "someone changed the git mode" is a
      // product question, "to what" is their business (src/main/telemetry.ts).
      // Only a field whose value actually moved: the renderer re-sends
      // `layout` and `sidebar` on every pane drag, and a patch that restates
      // a value is not a change anyone made.
      for (const key of changedSettingsKeys(previous, next, patch)) {
        track({ name: "settings_changed", key });
      }
      return next;
    },
    fallbacks: settingsFallbacks,
  },

  window: {
    state: () => settings.windowState(),
  },

  ui: {
    ready: (_request: void, ctx: IpcContext) => takeQueuedCommands(ctx.sender),
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

    showItemInFolder: revealProjectDirectory,
  },

  // A phase's handlers live in their own file and are spread in, exactly as
  // its branch of the contract is (src/shared/ipc/index.ts).
  ...explorerHandlers,
  ...gitHandlers,
  ...cadHandlers,
  ...integrationHandlers,
  ...clipboardHandlers,
  ...browserHandlers,
} satisfies Parameters<typeof registerIpc<IpcContract>>[1];

// The words on the native chooser are the words on the control that opened
// it — `Open folder…`, on the project chip's menu and the two empty states.
const openProjectDialog = {
  title: "Open folder",
  buttonLabel: "Open folder",
  properties: ["openDirectory", "createDirectory"],
} as const satisfies Electron.OpenDialogOptions;

// Settings › General › "Where the Open folder chooser opens". A folder that
// has since been moved or deleted is left out, so the chooser opens where the
// OS would have put it rather than on an error.
async function defaultPathOption(): Promise<{ defaultPath?: string }> {
  const defaultPath = await existingPath(settings.get().defaultProjectFolder ?? undefined, { directory: true });
  return defaultPath === undefined ? {} : { defaultPath };
}

export function registerIpcHandlers() {
  // The watcher and the pty manager push events, so they are handed the
  // broadcaster rather than reaching back for it.
  initExplorerServices(broadcast);
  registerIpc(ipcContract, handlers);
  installE2eDoor();
  // Boot is a settings change like any other: the login item, the menu-bar
  // item and the window's vibrancy have to match what is stored before the
  // first window is shown.
  applySettingsEffects(settings.get());
}

