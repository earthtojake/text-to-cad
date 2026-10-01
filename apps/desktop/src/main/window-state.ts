/**
 * Window geometry that survives a quit.
 *
 * Saves are debounced because resizing fires continuously, and the position is
 * checked against the displays that exist *now* — an app that reopens
 * off-screen after a monitor is unplugged looks like it failed to launch.
 */
import { screen, type BrowserWindow, type Rectangle } from "electron";

import type { WindowState } from "../shared/types";
import { settings } from "./db/repositories";

const SAVE_DEBOUNCE_MS = 400;

/** Every tracked window's final save, run once by `flushWindowStates`. */
const flushers = new Set<() => void>();

/**
 * How much of a window has to be on a display to count as on it: enough to
 * find and grab. A window saved on a monitor that is gone can overlap the
 * laptop's screen by a pixel, and a pixel is not a window.
 */
const MIN_VISIBLE_PX = 100;

/** The smallest a window may be (`minWidth`/`minHeight` in src/main/index.ts). */
export const WINDOW_MIN = { width: 900, height: 600 } as const;

/**
 * The stored geometry, fitted to the displays that exist now: centred when
 * too little of it is on any of them, and never larger than the work area of
 * the display it opens on — a window sized for a 2560px monitor does not fit
 * a laptop — unless that is smaller than the window's minimum.
 *
 * Except a window that is never shown (`TEXT_TO_CAD_E2E_HIDDEN=1`, src/main/index.ts):
 * it is on no display, so there is nothing to fit it to. Fitted anyway, the e2e
 * suite's window took the size of whatever screen the machine had — a CI
 * runner's 1024px one — and every layout the suite asserts moved with it.
 */
export function restoreWindowState(): WindowState {
  const state = settings.windowState();
  if (process.env.TEXT_TO_CAD_E2E_HIDDEN === "1") {
    return state;
  }
  const display = state.x === undefined || state.y === undefined ? undefined : mostOf(state);
  if (!display) {
    // Centred, which Electron does on the primary display.
    return { ...fit(state, screen.getPrimaryDisplay().workArea), x: undefined, y: undefined };
  }
  const area = display.workArea;
  const size = fit(state, area);
  // Shrunk, it may still hang off the far edge; slide it back on.
  return {
    ...size,
    x: Math.max(area.x, Math.min(state.x!, area.x + area.width - size.width)),
    y: Math.max(area.y, Math.min(state.y!, area.y + area.height - size.height)),
  };
}

/** The display holding the most of the window, if any holds enough of it. */
function mostOf(state: WindowState) {
  let best: { display: Electron.Display; area: number } | undefined;
  for (const display of screen.getAllDisplays()) {
    const { width, height } = intersection(display.workArea, state);
    if (width >= MIN_VISIBLE_PX && height >= MIN_VISIBLE_PX && width * height > (best?.area ?? 0)) {
      best = { display, area: width * height };
    }
  }
  return best?.display;
}

/**
 * No larger than the work area, and no smaller than the minimum: on a work
 * area under the minimum Electron sizes the window up to it anyway, and the
 * slide back on screen has to use the size the window will really have.
 */
function fit(state: WindowState, area: Rectangle): WindowState {
  return {
    ...state,
    width: Math.max(WINDOW_MIN.width, Math.min(state.width, area.width)),
    height: Math.max(WINDOW_MIN.height, Math.min(state.height, area.height)),
  };
}

/** Track a window and persist its geometry. Returns a detach function. */
export function trackWindowState(window: BrowserWindow) {
  let timer: NodeJS.Timeout | undefined;

  const save = () => {
    if (window.isDestroyed()) {
      return;
    }
    // getNormalBounds is the un-maximised, un-fullscreened rectangle: the one
    // to restore to when the user un-maximises later.
    const bounds = window.getNormalBounds();
    // Also reached from a timer, where a throw is an uncaught exception: a
    // save that cannot be written is logged and dropped.
    try {
      settings.setWindowState({
        x: bounds.x,
        y: bounds.y,
        width: bounds.width,
        height: bounds.height,
        maximized: window.isMaximized(),
      });
    } catch (error) {
      console.warn("[window-state] not saved:", error instanceof Error ? error.message : error);
    }
  };

  let flushed = false;
  const scheduleSave = () => {
    clearTimeout(timer);
    // After the quit flush the database is closing; a resize or move the
    // closing window still emits is not saved.
    if (!flushed) {
      timer = setTimeout(save, SAVE_DEBOUNCE_MS);
    }
  };

  const flush = () => {
    clearTimeout(timer);
    if (!flushed) {
      flushed = true;
      save();
    }
  };
  flushers.add(flush);

  window.on("resize", scheduleSave);
  window.on("move", scheduleSave);
  window.on("maximize", scheduleSave);
  window.on("unmaximize", scheduleSave);
  // The debounce would lose the last change on quit, so close saves directly —
  // unless quitting already did: `before-quit` flushes (below) before the
  // database closes, and a save from this later `close` would need it open.
  window.on("close", () => {
    flush();
    flushers.delete(flush);
  });

  return () => {
    clearTimeout(timer);
    flushers.delete(flush);
  };
}

/**
 * Save every tracked window's geometry now, once. Called from `before-quit`
 * BEFORE `closeDb()`: the windows' own `close` events fire after it, when the
 * database is gone, and must not reopen it.
 */
export function flushWindowStates() {
  for (const flush of flushers) {
    flush();
  }
  flushers.clear();
}

function intersection(area: Rectangle, state: WindowState) {
  const x = state.x ?? 0;
  const y = state.y ?? 0;
  return {
    width: Math.max(0, Math.min(x + state.width, area.x + area.width) - Math.max(x, area.x)),
    height: Math.max(0, Math.min(y + state.height, area.y + area.height) - Math.max(y, area.y)),
  };
}
