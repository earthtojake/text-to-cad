/**
 * What the ⋯ after the file's name offers, as data: the file's path to the clipboard, and the file
 * shown in the desktop's file manager — each only where the host can do it, so an item that cannot
 * work is never offered. `ViewerNavbar.jsx` draws it; the host performs it.
 *
 * Pure, so `node --test` loads it without the bundler's aliases: the labels read the i18n core's
 * current locale directly (still no environment, no aliases), which is why they answer in the
 * viewer's language however the host runs this module.
 */

import { translate } from "../../i18n/core.js";

/** Every action the menu can carry. */
export const ENTRY_ACTIONS = Object.freeze(["copy-path", "reveal"]);

/**
 * @typedef {"copy-path"|"reveal"} EntryAction
 * @typedef {"darwin"|"win32"|"linux"} Platform
 * @typedef {{ action: EntryAction, label: string }} EntryMenuItem
 */

/** What the OS calls its file browser. */
export function revealLabel(platform) {
  switch (platform) {
    case "win32":
      return translate("file.revealExplorer");
    case "linux":
      return translate("file.revealFileManager");
    default:
      return translate("file.revealFinder");
  }
}

/**
 * The menu for the file on screen: the actions the host can perform, in a fixed order.
 *
 * @param {Platform} platform
 * @param {ReadonlySet<EntryAction>} capabilities What this host can perform.
 * @returns {EntryMenuItem[]}
 */
export function entryMenu(platform, capabilities) {
  return [{ action: "copy-path", label: translate("file.copyPath") }, { action: "reveal", label: revealLabel(platform) }]
    .filter((item) => capabilities.has(item.action));
}
