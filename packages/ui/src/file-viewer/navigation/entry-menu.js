/**
 * What the menu on a file or a folder offers, as data.
 *
 * One table for the tree's rows and the breadcrumb's crumbs, in BOTH apps, so
 * a file cannot have one menu in one place and another menu two hundred
 * pixels away — or one menu in the desktop app and a different one in the
 * standalone viewer. `EntryMenu.jsx` draws it; the host performs it; the unit
 * test reads it directly.
 *
 * The shape is the platform's: verbs first, the copies together, the edits
 * together, and the one destructive item alone at the bottom — the OS trash,
 * which is reversible, so there is no confirmation in front of it.
 *
 * ## Capabilities
 *
 * The two hosts can do different things. The desktop app has a filesystem and
 * an operating system behind it; a browser tab has neither, and an item that
 * cannot work is worse than an item that is not there. So the table is
 * filtered by a capability set rather than forked: every host gets the same
 * items in the same order, minus the ones it cannot perform. A section left
 * empty by the filter disappears with its separator.
 *
 * Pure, and imports only `@hardcore/core`, so `node --test` loads it without the
 * bundler's aliases.
 */
import { isCadFile } from "@hardcore/core/lib/fileFormats.js";

/** Every action a menu can carry, in no particular order. */
export const ENTRY_ACTIONS = Object.freeze([
  "open",
  "open-default",
  "open-with",
  "reveal",
  "copy-path",
  "copy-relative-path",
  "copy-reference",
  "new-file",
  "new-folder",
  "open-terminal",
  "rename",
  "duplicate",
  "trash"
]);

/**
 * Everything, for a host with a real filesystem and an OS to hand it to: the
 * desktop app.
 */
export const ALL_ENTRY_CAPABILITIES = Object.freeze(new Set(ENTRY_ACTIONS));

/**
 * What a browser tab can honestly do.
 *
 * No `open with`, no `reveal`, no terminal — a web page has no OS to ask. No
 * rename, duplicate, new file or trash — the CAD Viewer's backend serves a
 * directory, it does not edit one, and an item that reports "not supported"
 * is a promise the app never made. What is left is opening a file and putting
 * a name for it on the clipboard, which is all a reader of a served directory
 * wants. `copy-path` is included because the standalone's backend can answer
 * with an absolute path when it is serving a local directory; a host that
 * cannot should drop it from its own set.
 */
export const WEB_ENTRY_CAPABILITIES = Object.freeze(
  new Set(["open", "copy-path", "copy-relative-path", "copy-reference"])
);

/**
 * The three items that do not act but start an inline field instead. The tree
 * draws that field itself, and a menu closing over one must not take the
 * focus back (`EntryMenu.jsx`).
 */
export const FIELD_ENTRY_ACTIONS = Object.freeze(new Set(["rename", "new-file", "new-folder"]));

/**
 * @typedef {"open"|"open-default"|"open-with"|"reveal"|"copy-path"|"copy-relative-path"|"copy-reference"|"new-file"|"new-folder"|"open-terminal"|"rename"|"duplicate"|"trash"} EntryAction
 * @typedef {"darwin"|"win32"|"linux"} Platform
 *
 * @typedef {object} EntryMenuItem
 * @property {EntryAction} action
 * @property {string} label
 * @property {boolean} [destructive]
 * @property {string} [shortcut] Printed at the right, the platform's way; the tree answers to it too.
 *
 * @typedef {object} MenuEntryTarget
 * @property {string} path Root-relative; `""` is the root itself, which has no rename and no trash.
 * @property {"file"|"directory"} kind
 * @property {"tree"|"crumb"} [surface]
 *   Where the menu was asked for. A breadcrumb names what the tab already
 *   shows, so its menu has no Open; the tree's rows do. Default: the tree.
 */

/** What the OS calls its file browser. */
export function revealLabel(platform) {
  switch (platform) {
    case "win32":
      return "Show in Explorer";
    case "linux":
      return "Show in file manager";
    default:
      return "Reveal in Finder";
  }
}

/**
 * The menu, as sections; the component draws a separator between them.
 *
 * @param {MenuEntryTarget} target
 * @param {Platform} platform
 * @param {ReadonlySet<EntryAction>} [capabilities] What this host can perform.
 * @returns {EntryMenuItem[][]}
 */
export function entryMenu(target, platform, capabilities = ALL_ENTRY_CAPABILITIES) {
  const trashShortcut = platform === "darwin" ? "⌘⌫" : "Ctrl+Del";
  const rename = { action: "rename", label: "Rename", shortcut: "F2" };
  const trash = { action: "trash", label: "Move to Trash", destructive: true, shortcut: trashShortcut };
  const copies = [
    { action: "copy-path", label: "Copy path" },
    { action: "copy-relative-path", label: "Copy relative path" }
  ];

  const sections = target.kind === "directory"
    ? directorySections({ target, platform, rename, trash, copies })
    : fileSections({ target, platform, rename, trash, copies });

  // Filter last, and by section, so an item's PLACE never depends on which
  // host is asking: the same action sits under the same neighbours
  // everywhere, and a section nothing survives takes its separator with it.
  return sections
    .map((section) => section.filter((item) => capabilities.has(item.action)))
    .filter((section) => section.length > 0);
}

function directorySections({ target, platform, rename, trash, copies }) {
  const root = target.path === "";
  return [
    [
      { action: "new-file", label: "New file" },
      { action: "new-folder", label: "New folder" },
      { action: "open-terminal", label: "Open in terminal" }
    ],
    [{ action: "reveal", label: revealLabel(platform) }],
    copies,
    ...(root ? [] : [[rename], [trash]])
  ];
}

function fileSections({ target, platform, rename, trash, copies }) {
  // One tab per file (the store dedupes), so there is no "open in new tab";
  // and a crumb IS the open file, so it does not offer Open at all.
  return [
    ...(target.surface === "crumb" ? [] : [[{ action: "open", label: "Open" }]]),
    [
      { action: "open-default", label: "Open with default app" },
      { action: "open-with", label: "Open with…" },
      { action: "reveal", label: revealLabel(platform) }
    ],
    // A CAD file is something an agent's prompt can point at: its reference is
    // the token the agent reads. Which files those are is `@hardcore/core`.
    [...copies, ...(isCadFile(target.path) ? [{ action: "copy-reference", label: "Copy reference" }] : [])],
    [rename, { action: "duplicate", label: "Duplicate" }],
    [trash]
  ];
}

/** Every action a menu carries, flat — for a caller checking one is offered. */
export function entryMenuActions(target, platform, capabilities = ALL_ENTRY_CAPABILITIES) {
  return entryMenu(target, platform, capabilities).flat().map((item) => item.action);
}
