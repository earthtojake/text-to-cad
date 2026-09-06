/**
 * Main. Owns the window, the menu, the database and every side effect; the
 * renderer is pure UI over IPC (plan §4).
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { BrowserWindow, app, shell } from "electron";

import { closeDb, db } from "./db";
import { registerIpcHandlers } from "./ipc";
import { shutdownAcp } from "./ipc/acp";
import { shutdownAgents } from "./ipc/agents";
import { installMenu } from "./menu";
import { disposeSettingsEffects } from "./settings-effects";
import { initTelemetry, track } from "./telemetry";
import { initUpdater, stopUpdater } from "./updater";
import { restoreWindowState, trackWindowState } from "./window-state";

const dirname = path.dirname(fileURLToPath(import.meta.url));

/** electron-vite sets this in `dev`; it is absent in every built app. */
const RENDERER_DEV_URL = process.env.ELECTRON_RENDERER_URL;

function createWindow() {
  const state = restoreWindowState();

  const window = new BrowserWindow({
    x: state.x,
    y: state.y,
    width: state.width,
    height: state.height,
    minWidth: 900,
    minHeight: 600,
    // The chrome is the app's own: on macOS the traffic lights sit inside the
    // sidebar's top strip (--titlebar-height in globals.css). Other platforms
    // keep their native frame, because a hand-drawn one there is a liability.
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    trafficLightPosition: process.platform === "darwin" ? { x: 14, y: 14 } : undefined,
    backgroundColor: "#0a0a0a",
    // Nothing is painted until the renderer has something to paint, so the
    // window never flashes an empty frame.
    show: false,
    webPreferences: {
      preload: path.join(dirname, "../preload/index.mjs"),
      // The preload is an ES module, which Electron only loads with the
      // sandbox off. Context isolation — the setting that actually keeps the
      // renderer away from Node — stays on, and the bridge exposes exactly one
      // frozen object (src/preload/index.ts).
      sandbox: false,
      contextIsolation: true,
      nodeIntegration: false,
      spellcheck: false,
    },
  });

  if (state.maximized) {
    window.maximize();
  }
  trackWindowState(window);

  window.once("ready-to-show", () => window.show());

  // A link in agent output, a file the viewer renders, an ad in a webview:
  // none of them get to open an Electron window. http(s) goes to the user's
  // browser; anything else is dropped.
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://") || url.startsWith("https://")) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, url) => {
    const current = window.webContents.getURL();
    if (url !== current) {
      event.preventDefault();
    }
  });

  if (RENDERER_DEV_URL) {
    void window.loadURL(RENDERER_DEV_URL);
  } else {
    void window.loadFile(path.join(dirname, "../renderer/index.html"));
  }

  return window;
}

// One window at a time owns the app's project list and database; a second
// instance would fight it. The second launch focuses the first.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    const [window] = BrowserWindow.getAllWindows();
    if (window) {
      if (window.isMinimized()) {
        window.restore();
      }
      window.focus();
    }
  });

  void app.whenReady().then(() => {
    app.setName("Hardcore");
    // Opening (and migrating) before the first window means the renderer's
    // first `projects.list` cannot race the schema.
    db();
    registerIpcHandlers();
    installMenu(() => BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0] ?? null);
    initTelemetry();
    createWindow();
    initUpdater();
    track({ name: "app_launched" });

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  app.on("before-quit", () => {
    stopUpdater();
    shutdownAcp();
    shutdownAgents();
    disposeSettingsEffects();
    closeDb();
  });
}
