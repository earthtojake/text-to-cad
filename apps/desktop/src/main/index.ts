/**
 * Main. Owns the window, the menu, the database and every side effect; the
 * renderer is pure UI over IPC (plan §4).
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { BrowserWindow, app, nativeImage, nativeTheme, shell } from "electron";

import { initCad, shutdownCad } from "./cad";
import { endTrackedChildren, killTrackedChildren } from "./children";
import { closeDb, databaseFile, db } from "./db";
import { settings as settingsRepository } from "./db/repositories";
import { broadcast, registerIpcHandlers } from "./ipc";
import { prewarmAgents, shutdownAcp } from "./ipc/acp";
import { shutdownAgents } from "./ipc/agents";
import { disposeExplorerServices } from "./ipc/explorer";
import { installMenu } from "./menu";
import { armQuitDeadline } from "./quit-deadline";
import { disposeSettingsEffects } from "./settings-effects";
import { initTelemetry, track } from "./telemetry";
import { initUpdater, stopUpdater } from "./updater";
import { TITLEBAR_HEIGHT, trafficLightPosition } from "../shared/titlebar";
import { restoreWindowState, trackWindowState } from "./window-state";

const dirname = path.dirname(fileURLToPath(import.meta.url));

/** electron-vite sets this in `dev`; it is absent in every built app. */
const RENDERER_DEV_URL = process.env.ELECTRON_RENDERER_URL;

/**
 * The one icon source, `build/icon.png` (scripts/make-icons.mjs). A packaged
 * app carries it as the bundle's icon and never reads this file; an
 * unpackaged one — `npm run dev`, `npx electron .` — runs inside Electron's
 * own binary and would show Electron's icon in the Dock and the taskbar
 * without being told otherwise.
 */
const DEV_ICON = path.resolve(dirname, "..", "..", "build", "icon.png");

/**
 * The window's own ground: `--background` of the theme the renderer is about
 * to paint, so the frame Electron shows before the page has any colour is not
 * a colour the page will never have.
 *
 * It used to be the dark value unconditionally, which was a black flash for a
 * person on Light — and the renderer's own first paint was a light flash for
 * everyone else, because the class arrives with React's first effect. Both
 * halves read the same preference now (`src/renderer/hooks/use-theme.ts`
 * applies it before render); `system` is resolved here through `nativeTheme`,
 * which is the same answer `prefers-color-scheme` gives the renderer.
 */
function windowBackgroundColor(): string {
  let preference: "system" | "light" | "dark" = "system";
  try {
    preference = settingsRepository.get().theme;
  } catch {
    // No database yet is not a reason to refuse to open a window.
  }
  const dark = preference === "system" ? nativeTheme.shouldUseDarkColors : preference === "dark";
  return dark ? "#0a0a0a" : "#ffffff";
}

/**
 * The app's name decides its data directory (`appData/<name>`), and Electron
 * takes the name from whichever package.json it happened to load: the
 * packaged app's, `apps/desktop`'s under `electron .`, and NOTHING under
 * `electron out/main/index.js` (then the name is "Electron" and the database
 * lands in a directory called that). Every launch of this code is Hardcore,
 * so the name and the directory are set here, before the single-instance
 * lock (which lives in that directory) and before the database opens. A
 * `--user-data-dir` on the command line — the e2e suite's — still wins.
 */
app.setName("Hardcore");
if (!app.commandLine.hasSwitch("user-data-dir")) {
  app.setPath("userData", path.join(app.getPath("appData"), "Hardcore"));
  app.setPath("sessionData", app.getPath("userData"));
}

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
    // Pinned, and vertically centred in the strip (src/shared/titlebar.ts).
    // Pinning fixes where the cluster starts; how wide it is stays AppKit's
    // business, which is why the renderer measures the rest rather than
    // trusting a number typed into the CSS.
    ...(process.platform === "darwin"
      ? {
          trafficLightPosition: trafficLightPosition(),
          // Not a bar Electron draws — on macOS this only asks Chromium to
          // publish the region the window controls occupy, as the Window
          // Controls Overlay geometry. `src/renderer/lib/titlebar.ts` reads it
          // and sets `--titlebar-inset` from it, so the leftmost pane's first
          // control clears the lights on a macOS that draws them wider.
          titleBarOverlay: { height: TITLEBAR_HEIGHT },
        }
      : {}),
    backgroundColor: windowBackgroundColor(),
    // Windows and Linux take the window's icon from here when unpackaged; a
    // packaged app has it in the executable and the desktop entry.
    ...(app.isPackaged ? {} : { icon: DEV_ICON }),
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
      // A window that is not on screen is still a window the app is working
      // in: an agent's stream, a terminal and the e2e suite's unshown window
      // (above) all need frames and unthrottled timers. Chromium slows both
      // to a crawl for a hidden window unless told otherwise.
      backgroundThrottling: false,
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

  // How the window arrives, in the three ways this app is launched (README,
  // "Windows nobody sees"):
  //
  // - `HARDCORE_E2E_HIDDEN=1`: never shown at all. The e2e suite drives the
  //   renderer through the DevTools protocol, which does not need a window on
  //   screen — and a suite that flashed one over the machine's screen for
  //   every spec is a suite nobody runs while working. `backgroundThrottling`
  //   is off below so the unshown window keeps painting and its timers keep
  //   real time.
  // - `HARDCORE_LAUNCH_INACTIVE=1`: shown, but without taking focus, for a
  //   relaunch from a script while the person is working in another app.
  // - otherwise: shown and focused, which is what a person double-clicking
  //   the app asked for.
  window.once("ready-to-show", () => {
    if (process.env.HARDCORE_E2E_HIDDEN === "1") {
      return;
    }
    if (process.env.HARDCORE_LAUNCH_INACTIVE === "1" || process.env.NODE_ENV === "test") {
      window.showInactive();
    } else {
      window.show();
    }
  });

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
    if (!app.isPackaged && process.platform === "darwin") {
      // The Dock shows Electron's icon for an unpackaged app; the packaged
      // one has the bundle's icon and needs nothing here.
      void app.dock?.setIcon(nativeImage.createFromPath(DEV_ICON));
    }
    // Opening (and migrating) before the first window means the renderer's
    // first `projects.list` cannot race the schema. The path is logged so a
    // "my projects are gone" report can be checked against the file that was
    // actually written.
    db();
    console.info(`[db] ${databaseFile()}`);
    registerIpcHandlers();
    // The CAD runtime, the skills root, the viewer manager and the MCP
    // bridge, before the first window: the file tab's first
    // `cad.viewerOrigin` and the first session's `mcpServers` and
    // `additionalDirectories` all need them up.
    await initCad({ sendCommand: (command) => broadcast("cad.command", command) });
    installMenu(() => BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0] ?? null);
    initTelemetry();
    createWindow();
    initUpdater();
    // One idle adapter per agent the index says is in use, a second and a
    // half from now: the first session opened then costs a `session/load`
    // and not a spawn (src/main/acp/warm.ts).
    prewarmAgents();
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

