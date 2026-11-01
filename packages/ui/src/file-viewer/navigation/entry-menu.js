/**
 * What a file's menus offer, as data — each item only where the host can do it, so an item that
 * cannot work is never offered; the host performs it. Two menus read it: a home card's ⋯
 * (`entryMenu`: Copy path, and the file shown in the desktop's file manager) and the navbar's ⋯
 * after the file's name (`ViewerNavbar.jsx`: Copy path, then Open in — `openInMenu`: the host's
 * browser page of the document, and the desktop's file manager by its name — then the host's own
 * items, the CAD viewer's Export).
 *
 * Pure, so `node --test` loads it without the bundler's aliases: the labels are in the language of
 * the `t` its caller hands it (`useI18n()`'s), English where it hands none.
 */

import { english } from "../../i18n/core.js";

/**
 * Every action a host can perform on a document: its path to the clipboard, the file shown in the
 * desktop's file manager, and the document's page opened in the person's browser (the CAD app's).
 */
export const ENTRY_ACTIONS = Object.freeze(["copy-path", "reveal", "browser"]);

/**
 * @typedef {"copy-path"|"reveal"|"browser"} EntryAction
 * @typedef {"darwin"|"win32"|"linux"} Platform
 * @typedef {{ action: EntryAction, label: string }} EntryMenuItem
 */

/** A home card's item that shows the file in the OS's file browser. */
export function revealLabel(platform, t = english) {
  switch (platform) {
    case "win32":
      return t("file.revealExplorer");
    case "linux":
      return t("file.revealFileManager");
    default:
      return t("file.revealFinder");
  }
}

/** What the OS calls its file browser: the navbar's Open in item that shows the file there. */
export function fileManagerName(platform, t = english) {
  switch (platform) {
    case "win32":
      return t("file.fileExplorer");
    case "linux":
      return t("file.fileManager");
    default:
      // A product's name, the same in every language.
      return "Finder";
  }
}

/**
 * A home card's file actions: Copy path, then the file shown in the file manager, each where the
 * host can do it, in a fixed order.
 *
 * @param {Platform} platform
 * @param {ReadonlySet<EntryAction>} capabilities What this host can perform.
 * @param {(key: string) => string} [t] The view's translator; English by default.
 * @returns {EntryMenuItem[]}
 */
export function entryMenu(platform, capabilities, t = english) {
  return [{ action: "copy-path", label: t("file.copyPath") }, { action: "reveal", label: revealLabel(platform, t) }]
    .filter((item) => capabilities.has(item.action));
}

/**
 * The navbar's Open in: the document's page in the person's browser, where the host has one, then
 * the desktop's file manager, by its name — each where the host can do it, in a fixed order.
 *
 * @param {Platform} platform
 * @param {ReadonlySet<EntryAction>} capabilities What this host can perform on the document on screen.
 * @param {(key: string) => string} [t] The view's translator; English by default.
 * @returns {EntryMenuItem[]}
 */
export function openInMenu(platform, capabilities, t = english) {
  return [{ action: "browser", label: t("file.browser") }, { action: "reveal", label: fileManagerName(platform, t) }]
    .filter((item) => capabilities.has(item.action));
}
