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
 * Every action a host can perform on a document: its path to the clipboard, a link to its page with
 * a fresh link to the clipboard, the file shown in the desktop's file manager, and the document's
 * page opened in the person's browser (the CAD app's).
 */
export const ENTRY_ACTIONS = Object.freeze(["copy-path", "copy-link", "reveal", "browser"]);

/**
 * @typedef {"copy-path"|"copy-link"|"reveal"|"browser"} EntryAction
 * @typedef {"darwin"|"win32"|"linux"} Platform
 * @typedef {{ action: EntryAction, label: string, enabled?: boolean, reason?: string }} EntryMenuItem
 *   `enabled` false: drawn disabled, `reason` its hint (Open in's entries; a home card's are always enabled).
 * @typedef {"places"|"source"|"exports"|"default"} OpenInGroup
 * @typedef {{ action: EntryAction|"app", label: string, enabled: boolean, reason?: string, group: OpenInGroup,
 *   target?: string, app?: string }} OpenInEntry  One place Open in opens the document in: an app's
 *   (`action: "app"`) names the file (`target`) and the app (`app`, or `"default"`, the OS's own).
 * @typedef {{ targets: readonly { target: string, kind: string, name: string, present: boolean,
 *   apps: readonly { id: string, name: string }[] }[], fileManager?: string }} OpenInFiles
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
 * A home card's actions: Copy path, Copy link, then the file shown in the file manager, each where
 * the host can do it, in a fixed order (a model's card, which has no file, takes Copy link alone).
 *
 * @param {Platform} platform
 * @param {ReadonlySet<EntryAction>} capabilities What this host can perform.
 * @param {(key: string) => string} [t] The view's translator; English by default.
 * @returns {EntryMenuItem[]}
 */
export function entryMenu(platform, capabilities, t = english) {
  return [{ action: "copy-path", label: t("file.copyPath") }, { action: "copy-link", label: t("file.copyLink") },
    { action: "reveal", label: revealLabel(platform, t) }]
    .filter((item) => capabilities.has(item.action));
}

/**
 * The navbar's Open in, as one list of entries in groups, in this order (a group with no entry is
 * left out, and the drawing parts groups with a separator):
 *
 *  - `places`: the document's page in the person's browser (the CAD app's), then the desktop's file
 *    manager, by its name -- each where the host can do it (`capabilities`);
 *  - `source`: the apps that take the document's source (a model's script, a file's own file), by
 *    their product names;
 *  - `exports`: each file a model's last build wrote that is on disk, its apps as "App (file name)";
 *  - `default`: Default app, the OS's own handler for the source.
 *
 * The apps come from the host (`files`, its answer for the document; null until and unless it
 * answers, when the menu is the places alone). Each entry says whether it opens now: what opens the
 * source -- the file manager, the source's apps, Default app -- is disabled, with the reason, while the
 * source was moved or deleted (`sourceMissing`, or the answer's `present: false`); the browser needs
 * none, and an export whose file is gone is left out.
 *
 * @param {Platform} platform
 * @param {ReadonlySet<EntryAction>} capabilities What this host can perform on the document on screen.
 * @param {(key: string, params?: Record<string, unknown>) => string} [t] The view's translator; English by default.
 * @param {{ sourceMissing?: boolean, files?: OpenInFiles | null }} [state] The document's source, and the host's apps for its files.
 * @returns {OpenInEntry[]}
 */
export function openInMenu(platform, capabilities, t = english, { sourceMissing = false, files = null } = {}) {
  const source = files?.targets?.find((item) => item.target === "source") ?? null;
  const missing = sourceMissing || source?.present === false;
  const opens = missing ? { enabled: false, reason: t("file.sourceMissing") } : { enabled: true };
  /** @type {OpenInEntry[]} */
  const entries = [
    { action: "browser", label: t("file.browser"), enabled: true, group: "places" },
    { action: "reveal", label: fileManagerName(platform, t), group: "places", ...opens },
  ].filter((item) => capabilities.has(/** @type {EntryAction} */ (item.action)));
  if (!files) return entries;
  for (const app of source?.apps ?? []) entries.push({ action: "app", label: app.name, group: "source", target: "source", app: app.id, ...opens });
  for (const exported of files.targets ?? []) {
    if (!exported.target.startsWith("export:") || !exported.present) continue;
    for (const app of exported.apps ?? []) {
      entries.push({ action: "app", label: `${app.name} (${exported.name})`, group: "exports", target: exported.target, app: app.id, enabled: true });
    }
  }
  if (source) entries.push({ action: "app", label: t("file.defaultApp"), group: "default", target: "source", app: "default", ...opens });
  return entries;
}
