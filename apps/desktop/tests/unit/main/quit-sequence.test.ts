import type { EventEmitter } from "node:events";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import type * as Children from "@main/children";
import { AgentDetector } from "@main/agents/detect";
import { AGENT_PROVIDERS } from "@main/agents/registry";
import { spawnProcessTerminal } from "@main/acp/process-backend";
import { SessionManager, type SessionRepository } from "@main/acp/sessions";
import { db } from "@main/db/index";
import type { AgentProvider } from "@shared/agents";
import type { Session } from "@shared/types";
import { cleanTempDirs, tempDir } from "./temp-dirs";

/**
 * The quit path of `src/main/index.ts`, with Electron's app and window modelled
 * as event emitters and the real `db()` / `closeDb()` / window-state tracking.
 * Every quit-time database write — the ACP snapshot flush in `shutdownAcp`
 * (`SessionManager.closeAll` → `flushAll`) and the window's geometry — has to
 * land before `closeDb()`, and nothing after it may reach for the database.
 */
const h = vi.hoisted(() => ({
  order: [] as string[],
  windows: [] as EventEmitter[],
  app: null as unknown as EventEmitter,
  manager: null as { closeAll(): void } | null,
  cadFails: false,
  /** The database handle's `close()` throws. */
  dbCloseFails: false,
  ready: false,
  /** `app.isReady()` at each call of Aptabase's `initialize`. */
  aptabaseInitReady: [] as boolean[],
  teardown: [] as string[],
  /** `armQuitDeadline`, the watchdog's arm. */
  arm: vi.fn(),
  electron: null as unknown as { dialog: { showErrorBox: ReturnType<typeof vi.fn> }; app: { exit: ReturnType<typeof vi.fn> } },
}));

vi.mock("electron", async () => {
  const { EventEmitter: Emitter } = await import("node:events");
  const app = Object.assign(new Emitter(), {
    setName: () => undefined,
    commandLine: { hasSwitch: () => true },
    setPath: () => undefined,
    getPath: () => "/nonexistent-userdata",
    requestSingleInstanceLock: () => true,
    // Ready on the first turn of the event loop after whenReady is asked for,
    // as in Electron: anything chained on it runs with isReady() true.
    whenReady: () =>
      Promise.resolve().then(() => {
        h.ready = true;
      }),
    isReady: () => h.ready,
    isPackaged: true,
    quit: () => undefined,
    exit: vi.fn(() => h.teardown.push("exit")),
  });
  h.app = app;
  class BrowserWindow extends Emitter {
    static getAllWindows = () => h.windows;
    static getFocusedWindow = () => null;
    // The window's session keeps the permission handlers it is given, so the
    // test can ask them what they answer.
    permissions = {} as { request?: (contents: unknown, permission: string, callback: (granted: boolean) => void) => void; check?: (contents: unknown, permission: string) => boolean };
    webContents = {
      setWindowOpenHandler: () => undefined,
      on: () => undefined,
      getURL: () => "",
      session: {
        setPermissionRequestHandler: (handler: never) => { this.permissions.request = handler; },
        setPermissionCheckHandler: (handler: never) => { this.permissions.check = handler; },
      },
    };
    constructor() {
      super();
      h.windows.push(this);
    }
    isDestroyed = () => false;
    isMaximized = () => false;
    maximize = () => undefined;
    getNormalBounds = () => ({ x: 0, y: 0, width: 900, height: 600 });
    loadFile = async () => undefined;
    loadURL = async () => undefined;
  }
  const dialog = { showErrorBox: vi.fn() };
  h.electron = { dialog, app };
  return {
    app,
    BrowserWindow,
    dialog,
    nativeImage: { createFromPath: () => ({}) },
    nativeTheme: { shouldUseDarkColors: false },
    shell: { openExternal: async () => undefined },
    screen: { getAllDisplays: () => [], getPrimaryDisplay: () => ({ workArea: { x: 0, y: 0, width: 1440, height: 900 } }) },
  };
});

vi.mock("better-sqlite3", () => ({
  default: class {
    pragma(source: string) {
      return source === "user_version" ? 0 : undefined;
    }
    close() {
      h.order.push("closeDb");
      h.teardown.push("database");
      if (h.dbCloseFails) {
        throw new Error("close failed");
      }
    }
  },
}));
vi.mock("@main/db/migrations", () => ({ MIGRATIONS: [{ version: 1 }], runMigrations: () => 1 }));
vi.mock("@main/db/repositories", async () => {
  const { db } = await import("@main/db/index");
  return {
    settings: {
      get: () => ({ theme: "system" }),
      windowState: () => ({ width: 900, height: 600 }),
      setWindowState: () => {
        db();
        h.order.push("windowState");
      },
    },
  };
});
vi.mock("@main/ipc/acp", () => {
  return {
    prewarmAgents: () => undefined,
    // `SessionManager.closeAll()`: every adapter closed, then the pending
    // snapshots written through the database.
    shutdownAcp: () => {
      h.manager?.closeAll();
    },
  };
});
vi.mock("@main/integrations", () => ({
  initIntegrations: async () => undefined,
  shutdownIntegrations: async () => void h.teardown.push("integrations"),
}));
vi.mock("@main/cad", () => ({
  initCad: async () => {
    if (h.cadFails) {
      throw new Error("the CAD runtime could not start");
    }
  },
  shutdownCad: async () => void h.teardown.push("cad"),
}));
vi.mock("@main/browser/service", () => ({ browserService: { dispose: () => undefined } }));
vi.mock("@main/children", async (importOriginal) => ({
  ...(await importOriginal<typeof Children>()),
  endTrackedChildren: () => void h.teardown.push("ended"),
  killTrackedChildren: () => void h.teardown.push("children"),
}));
vi.mock("@main/ipc", () => ({ broadcast: () => undefined, registerIpcHandlers: () => undefined }));
vi.mock("@main/ipc/agents", () => ({ shutdownAgents: () => undefined }));
vi.mock("@main/ipc/explorer", () => ({ disposeExplorerServices: () => undefined }));
vi.mock("@main/menu", () => ({ installMenu: () => undefined }));
vi.mock("@main/quit-deadline", () => ({ armQuitDeadline: h.arm }));
vi.mock("@main/settings-effects", () => ({ disposeSettingsEffects: () => undefined }));
// The real telemetry module over a fake Aptabase: which side of whenReady
// index.ts initializes it on is the bug this pins (Aptabase disables itself
// when `initialize` runs after ready).
vi.stubGlobal("__APTABASE_KEY__", "A-US-0000000000");
vi.mock("@aptabase/electron/main", () => ({
  initialize: async () => {
    h.aptabaseInitReady.push(h.ready);
  },
  trackEvent: async () => undefined,
}));
vi.mock("@main/updater", () => ({ initUpdater: () => undefined, stopUpdater: () => undefined }));

afterEach(() => {
  vi.useRealTimers();
  cleanTempDirs();
});

/** The fake ACP agent (`tests/fake-agent`), in the registry's claude-code slot. */
const FAKE_AGENT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "fake-agent", "index.mjs");
const claude = AGENT_PROVIDERS.find((provider) => provider.id === "claude-code")!;
(claude as { launch: AgentProvider["launch"] }).launch = { command: process.execPath, args: [FAKE_AGENT], env: {} };

/**
 * A session index and snapshot store that, like the app's, go through `db()`
 * on every call — so a write after `closeDb()` is the real error.
 */
function databaseBacked() {
  const rows = new Map<string, Session>();
  const late: string[] = [];
  const touch = (what: string) => {
    try {
      db();
    } catch (error) {
      late.push(what);
      throw error;
    }
  };
  const repo: SessionRepository = {
    list: () => (touch("list"), [...rows.values()]),
    get: (id) => (touch("get"), rows.get(id) ?? null),
    upsert: (session) => (touch("upsert"), rows.set(session.id, session), session),
    remove: (id) => (touch("remove"), void rows.delete(id)),
  };
  const snapshots = {
    read: () => (touch("snapshot.read"), null),
    write: () => {
      touch("snapshot.write");
      if (!h.order.includes("acpSnapshots")) {
        h.order.push("acpSnapshots");
      }
    },
    remove: () => touch("snapshot.remove"),
  };
  return { repo, snapshots, late };
}

async function managerWithSlowTurn() {
  const provider = { ...claude, launchWithoutBinary: true } as AgentProvider;
  const detector = new AgentDetector([provider], {
    env: async () => ({ PATH: process.env.PATH ?? "" }),
    isExecutable: async () => false,
    exists: async () => false,
    exec: async () => ({ stdout: "", stderr: "", code: 0 }),
    homeDir: () => os.homedir(),
    platform: process.platform,
  });
  await detector.refresh();
  const store = databaseBacked();
  const manager = new SessionManager({
    repo: store.repo,
    snapshots: store.snapshots,
    detector,
    spawnTerminal: spawnProcessTerminal,
    broadcast: () => undefined,
    newId: () => "session-1",
  });
  const cwd = await tempDir("text-to-cad-quit-");
  const session = await manager.create({ projectId: "p1", agentId: "claude-code", cwd, gitMode: "none" });
  // "slow" holds the turn open until cancelled: a prompt in flight at quit.
  const turn = manager.prompt(session.id, [{ type: "text", text: "slow" }]);
  await vi.waitFor(() => expect(manager.state(session.id)?.state.status).toBe("running"));
  return { manager, turn, late: store.late };
}

describe("quit sequence", () => {
  it("with a turn in flight: flushes ACP snapshots, then window state, then closes the database — and nothing touches it after", async () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { manager, turn, late } = await managerWithSlowTurn();
    h.manager = manager;
    const settled = turn.then(
      () => null,
      (error: unknown) => error,
    );

    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    await import("@main/index");
    await vi.waitFor(() => expect(h.windows).toHaveLength(1));
    // index.ts initialized Aptabase once, while the app was not yet ready.
    expect(h.ready).toBe(true);
    expect(h.aptabaseInitReady).toEqual([false]);
    const [window] = h.windows;

    // The app's page gets the clipboard and nothing else: Electron grants
    // whatever a session has no handler for — the camera, notifications.
    const { permissions } = window as unknown as { permissions: { request: (contents: unknown, permission: string, callback: (granted: boolean) => void) => void; check: (contents: unknown, permission: string) => boolean } };
    const granted = (permission: string) => {
      let answer: boolean | undefined;
      permissions.request(null, permission, (value) => { answer = value; });
      return answer;
    };
    expect(["media", "notifications", "geolocation", "display-capture", "fullscreen", "clipboard-read", "clipboard-sanitized-write"].map(granted))
      .toEqual([false, false, false, false, false, true, true]);
    expect(permissions.check(null, "media")).toBe(false);
    expect(permissions.check(null, "clipboard-read")).toBe(true);

    // A resize just before quit leaves a debounced save pending.
    window!.emit("resize");
    expect(() => h.app.emit("before-quit")).not.toThrow();
    expect(h.order).toEqual(["acpSnapshots", "windowState", "closeDb"]);

    // What Electron does next: the closing window may still move or resize
    // with no `close` yet to clear the debounce, the debounce's time passes,
    // will-quit runs, and only then does the window close. None of it reopens
    // the file, and no save is attempted (a failed one would warn).
    expect(() => {
      window!.emit("move");
      window!.emit("resize");
      vi.advanceTimersByTime(1_000);
      h.app.emit("will-quit");
    }).not.toThrow();
    expect(() => {
      window!.emit("close");
      vi.advanceTimersByTime(1_000);
    }).not.toThrow();
    expect(h.order).toEqual(["acpSnapshots", "windowState", "closeDb"]);
    expect(warn).not.toHaveBeenCalledWith(expect.stringContaining("[window-state]"), expect.anything());

    // The killed adapter's in-flight prompt rejects after the database closed;
    // its `prompt/error` must not try to write a status through it.
    vi.useRealTimers();
    const outcome = await settled;
    // The kill's own rejection, rethrown untouched: the failed turn reads
    // and writes nothing on its way out.
    expect(outcome).toBeInstanceOf(Error);
    expect(String(outcome)).toMatch(/exited during the turn/);
    expect(String(outcome)).not.toMatch(/closeDb/);
    expect(late).toEqual([]);

    // And a straggler that does reach for it gets a clear error, not a new connection.
    expect(() => db()).toThrow(/used after closeDb\(\)/);
    info.mockRestore();
    warn.mockRestore();
  });

  it("a startup failure outside the database tears down what started, says why without a database line, and exits", async () => {
    vi.resetModules();
    h.windows.length = 0;
    h.teardown.length = 0;
    h.cadFails = true;
    h.ready = false;
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    await import("@main/index");
    await vi.waitFor(() => expect(h.teardown).toContain("exit"));

    expect(h.electron.dialog.showErrorBox).toHaveBeenCalledWith("text-to-cad could not start", "the CAD runtime could not start");
    expect(h.electron.app.exit).toHaveBeenCalledWith(1);
    // app.exit skips before-quit and will-quit: their teardown ran first,
    // the database connection closed among it (the handle's own close()).
    expect(h.teardown).toEqual(["cad", "integrations", "database", "children", "exit"]);
    expect(h.windows).toHaveLength(0);
    error.mockRestore();
    info.mockRestore();
  });

  /** A fresh `@main/index` over a fresh app, with the process-level handlers it registers captured, not installed. */
  async function freshMain() {
    vi.resetModules();
    h.windows.length = 0;
    h.teardown.length = 0;
    h.cadFails = false;
    h.dbCloseFails = false;
    h.ready = false;
    h.arm.mockClear();
    // The app emitter outlives resetModules: earlier imports' listeners go.
    h.app.removeAllListeners();
    const handlers = new Map<string, (...args: unknown[]) => void>();
    const on = vi.spyOn(process, "on").mockImplementation(((event: string, handler: (...args: unknown[]) => void) => {
      handlers.set(event, handler);
      return process;
    }) as never);
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    await import("@main/index");
    await vi.waitFor(() => expect(h.windows).toHaveLength(1));
    on.mockRestore();
    const { markQuitting } = await import("@main/quitting");
    return { handlers, markQuitting, info, error, restore: () => [info, error].forEach((spy) => spy.mockRestore()) };
  }

  it("arms the quit deadline at before-quit, not only at will-quit: a stall between the two is bounded", async () => {
    const main = await freshMain();
    h.app.emit("before-quit");
    // will-quit never comes (a window that never acks its unload, a modal error dialog).
    expect(h.arm).toHaveBeenCalledTimes(1);
    // will-quit is a second arm, and arms nothing twice.
    h.app.emit("will-quit");
    expect(h.arm).toHaveBeenCalledTimes(1);
    expect(main.info).toHaveBeenCalledWith("[quit] will-quit");
    main.restore();
  });

  it("an uncaught exception logs; while quitting it also kills the children and exits, so no error dialog can hold the quit", async () => {
    const main = await freshMain();
    const uncaught = main.handlers.get("uncaughtException")!;
    expect(uncaught).toBeTypeOf("function");
    h.electron.app.exit.mockClear();

    uncaught(new Error("x"));
    expect(main.error).toHaveBeenCalledWith("[main] uncaught exception:", expect.any(Error));
    expect(h.electron.app.exit).not.toHaveBeenCalled();

    main.markQuitting();
    h.teardown.length = 0;
    uncaught(new Error("x"));
    expect(h.teardown).toEqual(["children", "exit"]);
    expect(h.electron.app.exit).toHaveBeenCalledWith(1);
    main.restore();
  });

  it("an uncaught exception outside a quit shows Electron's error box, since the listener took its dialog away", async () => {
    const main = await freshMain();
    const uncaught = main.handlers.get("uncaughtException")!;
    h.electron.dialog.showErrorBox.mockClear();
    // Under NODE_ENV=test a box would hold a suite run.
    uncaught(new Error("boom"));
    expect(h.electron.dialog.showErrorBox).not.toHaveBeenCalled();

    const mode = process.env.NODE_ENV;
    process.env.NODE_ENV = "production";
    try {
      uncaught(new Error("boom"));
    } finally {
      process.env.NODE_ENV = mode;
    }
    expect(h.electron.dialog.showErrorBox).toHaveBeenCalledWith(expect.any(String), expect.stringContaining("boom"));
    main.restore();
  });

  it("a teardown step that throws does not skip the rest of the quit: it is marked, the later steps run and the deadline is armed", async () => {
    const main = await freshMain();
    const { isQuitting } = await import("@main/quitting");
    h.teardown.length = 0;
    h.dbCloseFails = true;
    expect(() => h.app.emit("before-quit")).not.toThrow();
    expect(isQuitting()).toBe(true);
    // closeDb threw; the children still ended, and the deadline is armed.
    expect(h.teardown).toContain("ended");
    expect(h.arm).toHaveBeenCalledTimes(1);
    expect(main.error).toHaveBeenCalledWith("[main] quit teardown database:", expect.any(Error));
    main.restore();
  });
});
