/**
 * Main. Owns the window, the menu, the database and every side effect; the
 * renderer is pure UI over IPC (plan §4).
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { BrowserWindow, app, shell } from "electron";

import { cadRuntime, initCad, pluginManager, shutdownCad } from "./cad";
import { endTrackedChildren, killTrackedChildren } from "./children";
import { closeDb, db } from "./db";
import { broadcast, registerIpcHandlers } from "./ipc";
import { shutdownAcp } from "./ipc/acp";
import { detector, shutdownAgents } from "./ipc/agents";
import { disposeExplorerServices } from "./ipc/explorer";
import { installMenu } from "./menu";
import { armQuitDeadline } from "./quit-deadline";
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
    // Centred in a 32px strip (12px lights: 10 above, 10 below).
    trafficLightPosition: process.platform === "darwin" ? { x: 12, y: 10 } : undefined,
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
      // The explorer's browser tab is an Electron `<webview>` (plan §7). The
      // tag is off by default and has to be asked for; the guest it creates
      // is its own process with node integration off, which is why a browser
      // tab is a webview and not an iframe pointed at the open internet.
      webviewTag: true,
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

  void app.whenReady().then(async () => {
    app.setName("Hardcore");
    // Opening (and migrating) before the first window means the renderer's
    // first `projects.list` cannot race the schema.
    db();
    registerIpcHandlers();
    // The CAD runtime, the viewer manager and the MCP bridge, before the
    // first window: the file tab's first `cad.viewerOrigin` and the first
    // session's `mcpServers` both need them up.
    await initCad({ detector, sendCommand: (command) => broadcast("cad.command", command) });
    cadRuntime().onProgress((progress) => broadcast("runtime.progress", progress));
    schedulePluginInstall();
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

  /**
   * Quitting is a budget, not a sequence (tests/e2e/quit.spec.ts: under two
   * seconds with a repository watched, a shell, an adapter and the viewer all
   * up). Everything here is told to stop and nothing is awaited: the viewer,
   * the adapters and the ptys get their signals, the watcher and the bridge
   * start closing, the database closes — and then every child this process
   * still has a pipe to is detached, with the probes killed outright. Electron
   * waits for the Node side, and the Node side waits for its children; a
   * `--version` probe mid-`import cadgen` with a sixty-second timeout is what
   * made quitting take sixty seconds.
   */
  app.on("before-quit", () => {
    const started = Date.now();
    stopUpdater();
    // The viewers this app started, the bridge, and any tool call still
    // waiting on a window.
    void shutdownCad();
    shutdownAcp();
    shutdownAgents();
    disposeSettingsEffects();
    disposeExplorerServices();
    closeDb();
    endTrackedChildren();
    console.info(`[quit] teardown ${Date.now() - started}ms`);
  });

  // Whatever ignored its signal is not going to stop on its own — and
  // Chromium's own shutdown gets a deadline (src/main/quit-deadline.ts).
  app.on("will-quit", () => {
    killTrackedChildren();
    armQuitDeadline();
  });
}

/**
 * First launch and every app update (plan §8): install the bundled plugin
 * into each agent that is on the machine and has not been given this
 * version. Once the detector has probed, so "is Codex installed" has an
 * answer; off the launch path, because a `claude plugin install` takes
 * seconds and the window should not wait for it. Off entirely under test —
 * the e2e suite runs with a throwaway user-data directory but the user's
 * real `~/.claude` and `~/.codex`, and must not write to them.
 */
function schedulePluginInstall() {
  if (process.env.NODE_ENV === "test" || process.env.HARDCORE_NO_PLUGIN_INSTALL) {
    return;
  }
  const off = detector.onChange(() => {
    off();
    void pluginManager()
      .ensureInstalled()
      .then((installed) => {
        if (installed.length > 0) {
          console.info(
            `[plugin] ${installed.map((status) => `${status.agentId}: ${status.state}${status.message ? ` (${status.message})` : ""}`).join(", ")}`,
          );
          return pluginManager().statusAll().then((all) => broadcast("plugins.status", all));
        }
        return undefined;
      })
      .catch((error: unknown) => console.error("[plugin] install on launch failed", error));
  });
  detector.list();
}
