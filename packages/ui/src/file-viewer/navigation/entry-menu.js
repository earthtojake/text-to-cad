/**
 * What the menu on a file or a folder offers, as data.
 *
 * One table for the tree's rows and the breadcrumb's crumbs, in BOTH apps, so
 * a file cannot have one menu in one place and another menu two hundred
 * pixels away — or one menu in the desktop app and a different one in the
 * standalone viewer. `EntryMenu.jsx` draws it; the host performs it; the unit
 * test reads it directly.
 *
 * Path copies come first, followed by opening/reveal actions, the edits
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
 * Read-only browser actions. The local viewer can reveal files through its
 * guarded API; hosts without that capability omit it from their action map.
 */
export const WEB_ENTRY_CAPABILITIES = Object.freeze(
  new Set(["open", "reveal", "copy-path", "copy-relative-path"])
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
    copies,
    [
      { action: "new-file", label: "New file" },
      { action: "new-folder", label: "New folder" },
      { action: "open-terminal", label: "Open in terminal" }
    ],
    [{ action: "reveal", label: revealLabel(platform) }],
    ...(root ? [] : [[rename], [trash]])
  ];
}

function fileSections({ target, platform, rename, trash, copies }) {
  // One tab per file (the store dedupes), so there is no "open in new tab";
  // and a crumb IS the open file, so it does not offer Open at all.
  return [
    copies,
    ...(target.surface === "crumb" ? [] : [[{ action: "open", label: "Open" }]]),
    [
      { action: "open-default", label: "Open with default app" },
      { action: "open-with", label: "Open with…" },
      { action: "reveal", label: revealLabel(platform) }
    ],
    [rename, { action: "duplicate", label: "Duplicate" }],
    [trash]
  ];
}

/** Every action a menu carries, flat — for a caller checking one is offered. */
export function entryMenuActions(target, platform, capabilities = ALL_ENTRY_CAPABILITIES) {
  return entryMenu(target, platform, capabilities).flat().map((item) => item.action);
}
