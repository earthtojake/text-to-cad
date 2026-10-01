/**
 * The one thing the renderer needs to know about the platform before its first
 * paint: whether macOS is drawing traffic lights over the top-left corner.
 *
 * Read from the user agent rather than from `app.info()` over IPC, because
 * that answer arrives a frame or two late and the sidebar would visibly shift.
 */
const agent = navigator.userAgent;
export const isMac = agent.includes("Macintosh");
/** The renderer's one platform answer: keyboard modifiers, the viewer's host environment and its entry menus. */
export const platform: "darwin" | "win32" | "linux" = isMac ? "darwin" : agent.includes("Windows") ? "win32" : "linux";

/**
 * The app's shortcut modifier: Command on macOS, Control elsewhere. Never
 * either one: on a Mac, Control in a text field is Emacs' — Ctrl+K kills to
 * the end of the line, Ctrl+N moves down one — and the app must not take it.
 */
export function isPrimaryModifier(event: Pick<KeyboardEvent, "metaKey" | "ctrlKey">): boolean {
  return isMac ? event.metaKey : event.ctrlKey;
}

/** Call once, before render. Drives `--titlebar-inset` in globals.css. */
export function applyPlatformClass() {
  document.documentElement.classList.toggle("platform-mac", isMac);
}
