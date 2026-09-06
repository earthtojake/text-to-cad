/**
 * The three settings that are not just a stored value: they have to be applied
 * to the operating system or to the window before they mean anything.
 *
 * Applied in one place, from one function, called at registration and again on
 * every settings write (`src/main/ipc/index.ts`). A toggle whose effect lived
 * in its own listener would be a toggle that is right at boot and wrong after a
 * change made from another window.
 */
import { BrowserWindow, Tray, app, nativeImage } from "electron";

import type { Settings } from "../shared/types";

let tray: Tray | null = null;

/**
 * Launch at login, the menu-bar item and macOS vibrancy, brought into line with
 * `settings`. Safe to call as often as the settings change: every step is a
 * comparison against what the OS already has.
 */
export function applySettingsEffects(settings: Settings): void {
  applyLaunchAtLogin(settings.launchAtLogin);
  applyMenuBarItem(settings.showInMenuBar);
  applyVibrancy(settings.translucentSidebar);
}

/** Drop the menu-bar item. Called on quit so it does not outlive the app. */
export function disposeSettingsEffects(): void {
  tray?.destroy();
  tray = null;
}

/**
 * A development run must not install a login item: the path it would register
 * is the Electron binary in `node_modules`, and it would keep launching after
 * the checkout moved.
 */
function applyLaunchAtLogin(enabled: boolean) {
  if (!app.isPackaged || process.platform === "linux") {
    return;
  }
  if (app.getLoginItemSettings().openAtLogin !== enabled) {
    app.setLoginItemSettings({ openAtLogin: enabled, openAsHidden: true });
  }
}

/**
 * The macOS menu-bar item: a title, not an icon.
 *
 * `build/` is electron-builder's `buildResources` and is not shipped inside the
 * app, so there is no icon file to load at run time; a template image would
 * have to be drawn here or copied into `out/`. A text title is what the menu
 * bar renders either way, and it is legible at every scale factor without one.
 */
function applyMenuBarItem(enabled: boolean) {
  if (process.platform !== "darwin") {
    return;
  }
  if (!enabled) {
    tray?.destroy();
    tray = null;
    return;
  }
  if (tray) {
    return;
  }
  try {
    tray = new Tray(nativeImage.createEmpty());
    tray.setTitle("◆");
    tray.setToolTip("Hardcore");
    tray.on("click", showWindow);
  } catch (error) {
    // A menu-bar item is a convenience; failing to make one is not a reason to
    // fail the settings write that asked for it.
    console.warn("[settings] could not create the menu bar item", error);
    tray = null;
  }
}

function showWindow() {
  const window = BrowserWindow.getAllWindows()[0];
  if (!window) {
    return;
  }
  if (window.isMinimized()) {
    window.restore();
  }
  window.show();
  window.focus();
}

/**
 * macOS vibrancy behind the window. The renderer paints the sidebar with an
 * alpha so the blur shows through (`.translucent-sidebar` in globals.css);
 * without this call that alpha would just reveal the opaque window background.
 */
function applyVibrancy(enabled: boolean) {
  if (process.platform !== "darwin") {
    return;
  }
  for (const window of BrowserWindow.getAllWindows()) {
    window.setVibrancy(enabled ? "sidebar" : null);
    window.setBackgroundColor(enabled ? "#00000000" : "#0a0a0a");
  }
}
