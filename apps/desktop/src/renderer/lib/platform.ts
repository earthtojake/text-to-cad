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

/** Call once, before render. Drives `--titlebar-inset` in globals.css. */
export function applyPlatformClass() {
  document.documentElement.classList.toggle("platform-mac", isMac);
}
