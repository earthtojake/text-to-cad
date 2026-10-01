/**
 * The application menu.
 *
 * Menu items that change the UI do not reach into the renderer's state; they
 * send a `ui.command` event and let the renderer decide what that means. The
 * menu and the keyboard shortcut and the command palette then all take the
 * same path, and only one of them can be wrong.
 */
import { Menu, app, dialog, shell, type BrowserWindow, type MenuItemConstructorOptions, type WebContents } from "electron";

import type { IpcEventPayload } from "../shared/ipc";
import { browserService } from "./browser/service";
import { emit } from "./ipc/register";
import { isQuitting, markQuitting } from "./quitting";

type UiCommand = IpcEventPayload<"ui.command">["command"];

/** Commands held for a page that is not listening yet, by the page. */
const queued = new WeakMap<WebContents, IpcEventPayload<"ui.command">[]>();

function queueCommand(contents: WebContents, payload: IpcEventPayload<"ui.command">) {
  queued.set(contents, [...(queued.get(contents) ?? []), payload]);
}

/** What `ui.ready` answers with: the commands held for this page, taken once. */
export function takeQueuedCommands(contents: WebContents): IpcEventPayload<"ui.command">[] {
  const commands = queued.get(contents) ?? [];
  queued.delete(contents);
  return commands;
}

const REPOSITORY_URL = "https://github.com/earthtojake/text-to-cad";

export function buildMenu(
  focusedWindow: () => BrowserWindow | null,
  openWindow: () => BrowserWindow,
  packaged = app.isPackaged,
) {
  const send = (command: UiCommand) => () => {
    const window = focusedWindow();
    if (window) {
      emit([window.webContents], "ui.command", { command });
    }
  };
  // New Session and Settings… are how a person gets back into the app, and
  // on macOS the menu outlives the last window. With no window they open one
  // and hold the command for it until its page asks (`ui.ready`, once its
  // listener is attached). Pushed at `did-finish-load` it could be dropped:
  // the page subscribes in a passive effect, which may run after the load. A
  // view toggle has nothing to act on in a window that was not there, so it
  // stays `send`.
  const sendOrOpen = (command: UiCommand) => () => {
    if (focusedWindow()) {
      send(command)();
      return;
    }
    const window = openWindow();
    queueCommand(window.webContents, { command });
  };

  const isMac = process.platform === "darwin";

  // Mod+W closes the explorer's active tab, and the window only when there is
  // no tab to close: the renderer answers the key first and the menu hears it
  // only when the renderer let it go. With focus inside an embedded browser
  // page the renderer never sees the key at all, so `role: "close"` closed
  // the whole window from a tab's page. The key goes to the app instead.
  const close: MenuItemConstructorOptions = {
    label: "Close",
    accelerator: "CmdOrCtrl+W",
    click: () => {
      const window = focusedWindow();
      if (!window) {
        return;
      }
      const forwarded = browserService.forwardFromFocused(window, {
        keyCode: "W",
        modifiers: [isMac ? "meta" : "control"],
      });
      if (!forwarded) {
        window.close();
      }
    },
  };

  const appMenu: MenuItemConstructorOptions[] = isMac
    ? [
        {
          label: app.name,
          submenu: [
            { role: "about" },
            { type: "separator" },
            { label: "Settings…", accelerator: "Cmd+,", click: sendOrOpen("open-settings") },
            { type: "separator" },
            { role: "services" },
            { type: "separator" },
            { role: "hide" },
            { role: "hideOthers" },
            { role: "unhide" },
            { type: "separator" },
            { role: "quit" },
          ],
        },
      ]
    : [];

  const template: MenuItemConstructorOptions[] = [
    ...appMenu,
    {
      label: "File",
      submenu: [
        { label: "New Session", accelerator: "CmdOrCtrl+N", click: sendOrOpen("new-session") },
        { type: "separator" },
        ...(isMac
          ? [close]
          : ([
              { label: "Settings…", accelerator: "Ctrl+,", click: sendOrOpen("open-settings") },
              { type: "separator" },
              { role: "quit" },
            ] as MenuItemConstructorOptions[])),
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" },
        { role: "redo" },
        { type: "separator" },
        { role: "cut" },
        { role: "copy" },
        { role: "paste" },
        { role: "selectAll" },
      ],
    },
    {
      label: "View",
      submenu: [
        {
          label: "Toggle Sidebar",
          accelerator: "CmdOrCtrl+B",
          click: send("toggle-sidebar"),
        },
        {
          label: "Toggle Explorer",
          accelerator: "CmdOrCtrl+Alt+B",
          click: send("toggle-explorer"),
        },
        { type: "separator" },
        // The top level's history — the threads and new-session screens the
        // session pane has shown. Declared here as well as in the renderer
        // because this accelerator is the one that fires with focus inside a
        // webview or a terminal.
        {
          label: "Back",
          accelerator: "CmdOrCtrl+[",
          click: send("navigate-back"),
        },
        {
          label: "Forward",
          accelerator: "CmdOrCtrl+]",
          click: send("navigate-forward"),
        },
        { type: "separator" },
        {
          label: "Command Palette…",
          accelerator: "CmdOrCtrl+K",
          click: send("command-palette"),
        },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
        // Cmd+R belongs to the embedded browser page that has focus, and to
        // nothing else: `role: "reload"` reloaded the app's own renderer from
        // inside a browser page, dropping unsaved drafts and leaving the
        // native pages painted over the new document.
        {
          label: "Reload Page",
          accelerator: "CmdOrCtrl+R",
          click: () => { browserService.reloadFocused(focusedWindow()); },
        },
        ...(packaged
          ? []
          : ([{
              // Development only, on a chord nothing else uses (Mod+Shift+R
              // opens a review tab). Unsaved drafts still ask first.
              label: "Reload App",
              accelerator: "CmdOrCtrl+Alt+R",
              click: () => { focusedWindow()?.webContents.reload(); },
            }] as MenuItemConstructorOptions[])),
        { role: "toggleDevTools" },
      ],
    },
    {
      label: "Window",
      submenu: isMac
        ? [
            { role: "minimize" },
            { role: "zoom" },
            { type: "separator" },
            { role: "front" },
          ]
        : [{ role: "minimize" }, { role: "zoom" }, close],
    },
    {
      role: "help",
      submenu: [
        {
          label: "text-to-cad on GitHub",
          click: () => {
            void shell.openExternal(REPOSITORY_URL);
          },
        },
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}

export function installMenu(focusedWindow: () => BrowserWindow | null, openWindow: () => BrowserWindow) {
  Menu.setApplicationMenu(buildMenu(focusedWindow, openWindow));
  // Registered here, before the first window: the menu's reload is what the
  // renderer's unsaved-draft guard exists for.
  app.on("before-quit", markQuitting);
  app.on("browser-window-created", (_event, window) => guardRendererUnload(window));
}

/**
 * The renderer refuses to unload while a document has unsaved text
 * (`src/renderer/state/live-documents.ts`). Electron would otherwise cancel
 * the reload or close silently. While quitting, teardown has already run
 * (`before-quit` in index.ts), so the unload always proceeds; otherwise the
 * person decides.
 */
export function guardRendererUnload(window: BrowserWindow, quitting = isQuitting) {
  window.webContents.on("will-prevent-unload", (event) => {
    if (quitting()) {
      event.preventDefault();
      return;
    }
    const choice = dialog.showMessageBoxSync(window, {
      type: "warning",
      buttons: ["Discard Changes", "Cancel"],
      defaultId: 1,
      cancelId: 1,
      message: "Discard unsaved changes?",
      detail: "A document open in this window has changes that are not saved.",
    });
    // preventDefault on this event ignores the page's refusal: the unload goes ahead.
    if (choice === 0) {
      event.preventDefault();
    }
  });
}
