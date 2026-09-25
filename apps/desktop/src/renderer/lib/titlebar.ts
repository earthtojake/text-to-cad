import { titlebarInset, type TitlebarOverlay } from "@shared/titlebar";

import { isMac } from "./platform";

/**
 * `--titlebar-inset`: the room the leftmost pane leaves for macOS's traffic
 * lights, measured rather than guessed.
 *
 * With `titleBarOverlay` set on the window (main), Chromium publishes the
 * geometry of the region the window controls occupy — the same Window Controls
 * Overlay API a PWA gets. Its rect starts where content may safely start, so
 * that x *is* the inset, whatever AppKit decided the buttons should be this
 * release. `globals.css` carries the measured constant as the value the first
 * frame uses; this replaces it with the reading, and follows it afterwards:
 * fullscreen takes the lights away and the geometry says so, so the strip
 * gets its 84 pixels back.
 *
 * Nothing outside macOS has traffic lights, so nothing outside macOS is
 * measured: `--titlebar-inset` stays the 0 that `:root` declares.
 */
export function trackTitlebarInset(): () => void {
  if (!isMac) {
    return () => {};
  }
  const controls = navigator.windowControlsOverlay;
  const apply = () => {
    const overlay: TitlebarOverlay | null = controls
      ? { visible: controls.visible, x: controls.getTitlebarAreaRect().x }
      : null;
    document.documentElement.style.setProperty("--titlebar-inset", `${titlebarInset(overlay)}px`);
  };
  apply();
  if (!controls) {
    return () => {};
  }
  // The window moving between displays, entering fullscreen, or a macOS that
  // draws the buttons somewhere else after an update: the geometry changes and
  // the strip follows it.
  controls.addEventListener("geometrychange", apply);
  return () => controls.removeEventListener("geometrychange", apply);
}
