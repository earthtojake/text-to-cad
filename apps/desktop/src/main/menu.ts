/**
 * The application menu.
 *
 * Menu items that change the UI do not reach into the renderer's state; they
 * send a `ui.command` event and let the renderer decide what that means. The
 * menu and the keyboard shortcut and the command palette then all take the
 * same path, and only one of them can be wrong.
 */
import { Menu, app, shell, type BrowserWindow, type MenuItemConstructorOptions } from "electron";

import type { IpcEventPayload } from "../shared/ipc";
import { emit } from "./ipc/register";

type UiCommand = IpcEventPayload<"ui.command">["command"];

const REPOSITORY_URL = "https://github.com/earthtojake/text-to-cad";

export function buildMenu(focusedWindow: () => BrowserWindow | null) {
  const send = (command: UiCommand) => () => {
    const window = focusedWindow();
    if (window) {
      emit([window.webContents], "ui.command", { command });
    }
  };

  const isMac = process.platform === "darwin";

  const appMenu: MenuItemConstructorOptions[] = isMac
    ? [
        {
          label: app.name,
          submenu: [
            { role: "about" },
            { type: "separator" },
            { label: "Settings…", accelerator: "Cmd+,", click: send("open-settings") },
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
        { label: "New Session", accelerator: "CmdOrCtrl+N", click: send("new-session") },
        { type: "separator" },
        ...(isMac
          ? ([{ role: "close" }] as MenuItemConstructorOptions[])
          : ([
              { label: "Settings…", accelerator: "Ctrl+,", click: send("open-settings") },
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
        { role: "reload" },
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
        : [{ role: "minimize" }, { role: "zoom" }, { role: "close" }],
    },
    {
      role: "help",
      submenu: [
        {
          label: "Hardcore on GitHub",
          click: () => {
            void shell.openExternal(REPOSITORY_URL);
          },
        },
      ],
    },
  ];

  return Menu.buildFromTemplate(template);
}

export function installMenu(focusedWindow: () => BrowserWindow | null) {
  Menu.setApplicationMenu(buildMenu(focusedWindow));
}
