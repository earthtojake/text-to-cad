/**
 * The one thing the renderer needs to know about the platform before its first
 * paint: whether macOS is drawing traffic lights over the top-left corner.
 *
 * Read from the user agent rather than from `app.info()` over IPC, because
 * that answer arrives a frame or two late and the sidebar would visibly shift.
 */
export const isMac = navigator.userAgent.includes("Macintosh");

/** Call once, before render. Drives `--titlebar-inset` in globals.css. */
export function applyPlatformClass() {
  document.documentElement.classList.toggle("platform-mac", isMac);
}
