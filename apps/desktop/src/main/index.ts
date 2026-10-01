/**
 * Main. Owns the window, the menu, the database and every side effect; the
 * renderer is pure UI over IPC (plan §4).
 */
import path from "node:path";
import { fileURLToPath } from "node:url";

import { BrowserWindow, app, dialog, nativeImage, nativeTheme, shell } from "electron";

import { initIntegrations, shutdownIntegrations } from "./integrations";
import { initCad, shutdownCad } from "./cad";
import { browserService } from "./browser/service";
import { endTrackedChildren, killTrackedChildren } from "./children";
import { closeDb, databaseFile, db, startupFailureMessage } from "./db";
import { settings as settingsRepository } from "./db/repositories";
import { broadcast, registerIpcHandlers } from "./ipc";
import { prewarmAgents, shutdownAcp } from "./ipc/acp";
import { shutdownAgents } from "./ipc/agents";
import { disposeExplorerServices } from "./ipc/explorer";
import { installMenu } from "./menu";
import { armQuitDeadline } from "./quit-deadline";
import { isQuitting, markQuitting } from "./quitting";
import { disposeSettingsEffects } from "./settings-effects";
import { initTelemetry, track } from "./telemetry";
import { initUpdater, stopUpdater } from "./updater";
import { TITLEBAR_HEIGHT, trafficLightPosition } from "../shared/titlebar";
import { WINDOW_MIN, flushWindowStates, restoreWindowState, trackWindowState } from "./window-state";

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
  return dark ? "#292929" : "#ffffff";
}

/**
 * The app's name decides its data directory (`appData/<name>`), and Electron
 * takes the name from whichever package.json it happened to load: the
 * packaged app's, `apps/desktop`'s under `electron .`, and NOTHING under
 * `electron out/main/index.js` (then the name is "Electron" and the database
 * lands in a directory called that). Every launch of this code is text-to-cad,
 * so the name and the directory are set here, before the single-instance
 * lock (which lives in that directory) and before the database opens. A
 * `--user-data-dir` on the command line — the e2e suite's — still wins.
 */
app.setName("text-to-cad");
if (!app.commandLine.hasSwitch("user-data-dir")) {
  app.setPath("userData", path.join(app.getPath("appData"), "text-to-cad"));
  app.setPath("sessionData", app.getPath("userData"));
}

/**
 * What the app's own page may ask Chromium for: the clipboard, which the
 * terminal pastes from and the sidebar's Copy path writes to. Nothing else —
 * not the camera or microphone the vendored AI Elements know how to ask for,
 * not notifications, not the screen — because the app uses none of it, and
 * Electron grants every request a session has no handler for. Browser pages
 * are in partitions of their own that refuse everything
 * (`src/main/browser/service.ts`); this is the app's `defaultSession`.
 */
const APP_PERMISSIONS: ReadonlySet<string> = new Set(["clipboard-read", "clipboard-sanitized-write"]);

export function restrictAppPermissions(session: Electron.Session) {
  session.setPermissionRequestHandler((_contents, permission, callback) => callback(APP_PERMISSIONS.has(permission)));
  session.setPermissionCheckHandler((_contents, permission) => APP_PERMISSIONS.has(permission));
}

function createWindow() {
  const state = restoreWindowState();

  const window = new BrowserWindow({
    x: state.x,
    y: state.y,
    width: state.width,
    height: state.height,
    minWidth: WINDOW_MIN.width,
    minHeight: WINDOW_MIN.height,
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
      // Browser pages are main-owned WebContentsViews, never renderer-created guests.
      webviewTag: false,
    },
  });

  restrictAppPermissions(window.webContents.session);
  if (state.maximized) {
    window.maximize();
  }
  trackWindowState(window);

  // How the window arrives, in the three ways this app is launched (README,
  // "Windows nobody sees"):
  //
  // - `TEXT_TO_CAD_E2E_HIDDEN=1`: never shown at all. The e2e suite drives the
  //   renderer through the DevTools protocol, which does not need a window on
  //   screen — and a suite that flashed one over the machine's screen for
  //   every spec is a suite nobody runs while working. `backgroundThrottling`
  //   is off below so the unshown window keeps painting and its timers keep
  //   real time.
  // - `TEXT_TO_CAD_LAUNCH_INACTIVE=1`: shown, but without taking focus, for a
  //   relaunch from a script while the person is working in another app.
  // - otherwise: shown and focused, which is what a person double-clicking
  //   the app asked for.
  window.once("ready-to-show", () => {
    if (process.env.TEXT_TO_CAD_E2E_HIDDEN === "1") {
      return;
    }
    if (process.env.TEXT_TO_CAD_LAUNCH_INACTIVE === "1" || process.env.NODE_ENV === "test") {
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

  // Before ready, or Aptabase disables itself (src/main/telemetry.ts).
  initTelemetry();

  // A rejection nobody awaited is a bug with no other trace; log it.
  process.on("unhandledRejection", (reason) => {
    console.error("[main] unhandled rejection:", reason);
  });

  // One teardown step, guarded: a throw (or a rejection) is logged and the
  // steps after it still run. Shared by the startup-failure path and the quit.
  const step = (phase: string, name: string, run: () => unknown) => {
    try {
      const result = run();
      if (result instanceof Promise) {
        result.catch((stepError: unknown) => console.error(`[main] ${phase} ${name}:`, stepError));
      }
    } catch (stepError) {
      console.error(`[main] ${phase} ${name}:`, stepError);
    }
  };

  // Electron raises its modal "A JavaScript error occurred" dialog for an
  // exception nobody caught only while no listener exists, and this listener
  // exists: so outside a quit it shows the box itself (a packaged app has no
  // console to read), and while quitting nobody is there to dismiss one — it
  // would hold the process before `will-quit` ever runs — so it logs and
  // leaves now.
  process.on("uncaughtException", (error) => {
    console.error("[main] uncaught exception:", error);
    if (isQuitting()) {
      killTrackedChildren();
      app.exit(1);
    } else if (app.isReady() && process.env.NODE_ENV !== "test") {
      try {
        dialog.showErrorBox("A JavaScript error occurred in the main process", error instanceof Error ? error.stack ?? error.message : String(error));
      } catch (dialogError) {
        console.error("[main] could not show the uncaught exception:", dialogError);
      }
    }
  });

  // Which step of startup is running, so a failure names the database file
  // only when the database is what failed.
  let startupStep: "database" | "services" = "database";
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
    startupStep = "services";
    console.info(`[db] ${databaseFile()}`);
    registerIpcHandlers();
    // The CAD runtime, the skills root, the viewer manager and the MCP
    // bridge, before the first window: the file tab's first
    // `cad.viewerOrigin` and the first session's `mcpServers` and
    // `additionalDirectories` all need them up.
    await initCad();
    await initIntegrations({ sendCommand: (command) => broadcast("integrations.command", command), cancelCommand: requestId => broadcast("integrations.cancel", { requestId }) });
    installMenu(() => BrowserWindow.getFocusedWindow() ?? BrowserWindow.getAllWindows()[0] ?? null, createWindow);
    createWindow();
    initUpdater();
    // Starts the agent probe now, and (outside `NODE_ENV=test` unless
    // `TEXT_TO_CAD_PREWARM=1`) spawns one idle adapter per agent the index says
    // is in use a second and a half from now, once the probe has settled: the
    // first session opened then costs a `session/load` and not a spawn
    // (src/main/acp/warm.ts).
    prewarmAgents();
    track({ name: "app_launched" });

    app.on("activate", () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });
  }).catch((error: unknown) => {
    // A migration that failed, a database from a newer build (refused, not
    // modified), a pre-upgrade backup on a full disk, the CAD runtime or the
    // bridge failing to start: without this the app sits in the Dock with no
    // window and no word. Say why and where, then leave.
    console.error("[main] startup failed:", error);
    try {
      dialog.showErrorBox("text-to-cad could not start", startupFailureMessage(error, startupStep === "database"));
    } catch (dialogError) {
      console.error("[main] could not show the startup error:", dialogError);
    }
    // `app.exit` skips before-quit and will-quit, so their teardown runs
    // here: what initCad and initIntegrations may already have started (the
    // runtime probe, a viewer, the bridge) must not outlive this process.
    // Each step is guarded — one failing must not keep the next from running.
    step("startup teardown", "cad", shutdownCad);
    step("startup teardown", "integrations", shutdownIntegrations);
    step("startup teardown", "database", closeDb);
    step("startup teardown", "children", killTrackedChildren);
    app.exit(1);
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });

  /**
   * Quitting is a budget, not a sequence: two seconds, with a repository
   * watched, a shell, an adapter and the viewer all up (tests/e2e/cad.spec.ts
   * quits in that state and asserts no child is left behind). Everything here is told to stop and nothing is awaited: the viewer,
   * the adapters and the ptys get their signals, the bridge starts closing,
   * the explorer's watchers are left open (chokidar's `close()` blocks, and an
   * fsevents handle dies with the process), the database closes — and then every child this process
   * still has a pipe to is detached, with the probes killed outright. Electron
   * waits for the Node side, and the Node side waits for its children; a
   * `--version` probe mid-`import cadgen` with a sixty-second timeout is what
   * made quitting take sixty seconds.
   */
  let quitStartedAt: number | undefined;
  // Armed once, at the end of `before-quit`; `will-quit` calls it too, as the fallback if `before-quit` threw before its `try`.
  let deadlineArmed = false;
  const armDeadline = () => {
    if (!deadlineArmed) {
      deadlineArmed = true;
      armQuitDeadline(quitStartedAt);
    }
  };
  app.on("before-quit", () => {
    // Before anything that can throw: menu.ts's own before-quit listener is
    // registered later and runs after this one, so a throw below would
    // otherwise leave `isQuitting()` false and the window guards asking.
    markQuitting();
    const started = Date.now();
    quitStartedAt = started;
    // Each step is guarded, and the deadline armed whatever happens: one
    // failing teardown must not skip the rest, the database close among them.
    try {
      step("quit teardown", "updater", stopUpdater);
      // The viewers this app started, the bridge, and any tool call still
      // waiting on a window.
      step("quit teardown", "cad", shutdownCad);
      step("quit teardown", "integrations", shutdownIntegrations);
      // Database writes on the way out, in this order and all before closeDb():
      // the ACP snapshot flush (closeAll → flushAll; each adapter's `closed`
      // status is dispatched synchronously and its later exit is ignored), then
      // the window geometry. Nothing after closeDb() may reach for the database.
      step("quit teardown", "acp", shutdownAcp);
      step("quit teardown", "agents", shutdownAgents);
      step("quit teardown", "settings effects", disposeSettingsEffects);
      step("quit teardown", "browser", () => browserService.dispose());
      step("quit teardown", "explorer", disposeExplorerServices);
      // Before the database closes: the windows' own `close` saves come after
      // this handler, and must not reopen it (src/main/window-state.ts).
      step("quit teardown", "window state", flushWindowStates);
      step("quit teardown", "database", closeDb);
      step("quit teardown", "children", endTrackedChildren);
      console.info(`[quit] teardown ${Date.now() - started}ms`);
    } finally {
      // Everything this app owns is saved and closed, and nothing can take the
      // quit back (no handler cancels it; the unload guard lets it through), so
      // the deadline starts here: a window that never acks its unload, or a
      // main-process error dialog, sits between `before-quit` and `will-quit`.
      armDeadline();
    }
  });

  // Whatever ignored its signal is not going to stop on its own — and
  // Chromium's own shutdown gets a deadline (src/main/quit-deadline.ts).
  app.on("will-quit", () => {
    console.info("[quit] will-quit");
    killTrackedChildren();
    armDeadline();
  });
}
