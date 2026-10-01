/**
 * The two keys Settings owns: `Cmd/Ctrl+,` opens it, `Escape` closes it.
 *
 * The app menu already carries the first as an accelerator, which is the copy
 * that works when the keyboard is inside a webview or a native dialog. This is
 * the copy that works when the menu is not (a hidden menu bar on Windows and
 * Linux, a full-screen window), and both end at the same store action — the
 * same arrangement the command palette uses for `Cmd+K`.
 */
import { useEffect } from "react";

import { useUi } from "@renderer/state/ui";

export function useSettingsShortcuts(): void {
  const openSettings = useUi((state) => state.openSettings);
  const closeSettings = useUi((state) => state.closeSettings);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "," && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        openSettings();
        return;
      }
      if (event.key === "Escape" && useUi.getState().route === "settings" && !overlayOpen()) {
        closeSettings();
      }
    };
    // Capture, not bubble. Radix closes its own dialog on Escape without
    // stopping the event, and React flushes that state change synchronously —
    // so by the time a bubble-phase listener ran, the drawer would already be
    // marked closed and `overlayOpen()` would say the coast was clear. In the
    // capture phase the question "is something on top of Settings?" is still
    // answerable, and the answer is the one the user can see.
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [openSettings, closeSettings]);
}

/**
 * Escape belongs to whatever is on top. Radix closes its own dialog, drawer or
 * select on the same keystroke without stopping it, so Escape with the agent
 * drawer open would otherwise close the drawer and Settings behind it.
 */
function overlayOpen(): boolean {
  return (
    document.querySelector(
      '[data-state="open"][role="dialog"], [data-state="open"][role="listbox"], [data-state="open"][role="menu"]',
    ) !== null
  );
}
