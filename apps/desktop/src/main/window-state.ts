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

/** The stored geometry, dropped back to defaults if it lands off-screen. */
export function restoreWindowState(): WindowState {
  const state = settings.windowState();
  if (state.x === undefined || state.y === undefined) {
    return state;
  }
  const visible = screen.getAllDisplays().some((display) => overlaps(display.workArea, state));
  return visible ? state : { ...state, x: undefined, y: undefined };
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
    settings.setWindowState({
      x: bounds.x,
      y: bounds.y,
      width: bounds.width,
      height: bounds.height,
      maximized: window.isMaximized(),
    });
  };

  const scheduleSave = () => {
    clearTimeout(timer);
    timer = setTimeout(save, SAVE_DEBOUNCE_MS);
  };

  window.on("resize", scheduleSave);
  window.on("move", scheduleSave);
  window.on("maximize", scheduleSave);
  window.on("unmaximize", scheduleSave);
  // The debounce would lose the last change on quit, so close saves directly.
  window.on("close", () => {
    clearTimeout(timer);
    save();
  });

  return () => {
    clearTimeout(timer);
  };
}

function overlaps(area: Rectangle, state: WindowState) {
  const x = state.x ?? 0;
  const y = state.y ?? 0;
  return (
    x < area.x + area.width &&
    x + state.width > area.x &&
    y < area.y + area.height &&
    y + state.height > area.y
  );
}
