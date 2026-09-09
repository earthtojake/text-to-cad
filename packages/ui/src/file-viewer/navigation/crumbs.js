/**
 * The file tab's breadcrumb, as data.
 *
 * The crumbs are the path segments BELOW the host's root, and nothing else:
 * `STL/link_plate.stl` is `STL › link_plate.stl`, with no crumb for the
 * directory the host is serving or the project the file sits in.
 *
 * Each crumb's menu is its NEIGHBOURS — the listing of its PARENT directory,
 * with the crumb's own entry marked. So the first crumb lists the root, a
 * folder crumb lists what sits beside that folder, and the file crumb lists
 * its siblings; the menus read as "what else is here, at this level" from
 * left to right, and a crumb never lists anything above the root. That is
 * why there is no root crumb: the root's neighbours are outside what the host
 * may show. A file at the root is one crumb, listing the root.
 *
 * Picking a file opens it; picking a folder opens a submenu of that folder.
 *
 * Pure: `Breadcrumbs.jsx` reads listings through its source adapter and draws
 * what this returns, and the unit test reads it directly.
 */

/** @typedef {"directory"|"file"|"ellipsis"} CrumbKind */

/**
 * @typedef {object} Crumb
 * @property {CrumbKind} kind
 * @property {string} label
 * @property {string} title The tooltip: the full segment, or the folded folders joined.
 * @property {string} path Root-relative path of what the crumb names; never `""`.
 * @property {string|null} menu
 *   The directory whose listing the crumb's menu shows — its parent, so the
 *   menu is the crumb's neighbours. `""` is the root. Null only for the
 *   ellipsis, which lists its folded folders instead.
 * @property {string|null} current
 *   The entry the menu marks: the crumb itself. Equal to
 *   `stepToward(menu, path)`, which is what the component computes from the
 *   open file — this field is the rule written down.
 * @property {{ label: string, path: string }[]} hidden
 *   Ellipsis only: the folders it stands for, each a submenu.
 */

/**
 * @param {object} input
 * @param {string|null} input.path The open file, root-relative; null for an empty tab.
 * @param {boolean} input.narrow
 *   Fold the folders into one `…` — a narrow pane. The file survives the
 *   fold: it is the crumb that names what is on screen.
 * @returns {Crumb[]}
 */
export function buildCrumbs({ path, narrow }) {
  const parts = path ? String(path).split("/").filter((part) => part !== "") : [];
  if (parts.length === 0) {
    return [];
  }
  const at = (index) => parts.slice(0, index + 1).join("/");
  const crumbs = parts.map((label, index) => {
    const own = at(index);
    return {
      kind: index === parts.length - 1 ? "file" : "directory",
      label,
      title: label,
      path: own,
      menu: parentOf(own),
      current: own,
      hidden: []
    };
  });

  const folders = crumbs.slice(0, -1);
  if (!narrow || folders.length < 2) {
    return crumbs;
  }
  const ellipsis = {
    kind: "ellipsis",
    label: "…",
    title: folders.map((folder) => folder.label).join("/"),
    path: folders[folders.length - 1].path,
    menu: null,
    current: null,
    hidden: folders.map((folder) => ({ label: folder.label, path: folder.path }))
  };
  return [ellipsis, crumbs[crumbs.length - 1]];
}

/**
 * The worktree marker, drawn before the crumbs, or null for a tab in the
 * project directory.
 *
 * NOT a crumb: it names the root, and a root has no menu here — its
 * neighbours are outside the project. It is a label, because which copy of
 * the tree a file is in is the one thing a person cannot tell from its name,
 * and losing that with the project crumb would have been an accident rather
 * than a decision.
 *
 * Only a host with several copies of one tree has anything to put here; the
 * standalone viewer serves one directory and passes nothing.
 *
 * @param {string|null} root
 * @returns {{ label: string, title: string }|null}
 */
export function worktreeMark(root) {
  return root ? { label: root.split(/[\\/]/).pop() ?? root, title: root } : null;
}

/**
 * @typedef {object} ListingEntry
 * @property {string} path Root-relative path.
 * @property {string} name The label.
 * @property {"file"|"directory"} kind
 * @property {unknown} [value] The host's own payload, handed back on open.
 */

/**
 * @typedef {ListingEntry & { current: boolean }} MenuEntry
 *   `current` marks the entry on the way to the open file.
 */

const COLLATOR = new Intl.Collator("en", { numeric: true, sensitivity: "base" });

/**
 * A listing as a menu: directories first, then files, each in natural order,
 * with the current entry marked. A source that sorts already sorts again for
 * nothing, which is cheap, and makes the menu's order a fact of this module
 * rather than of whichever listing it was handed.
 *
 * @param {readonly ListingEntry[]} entries
 * @param {string|null} current
 * @returns {MenuEntry[]}
 */
export function menuEntries(entries, current) {
  return [...entries]
    .sort((left, right) =>
      left.kind !== right.kind
        ? (left.kind === "directory" ? -1 : 1)
        : COLLATOR.compare(left.name, right.name)
    )
    .map((entry) => ({ ...entry, current: entry.path === current }));
}

/**
 * The entry in `directory` that lies on the way to `target`: the target
 * itself when it is a direct child, the next folder down when it is deeper,
 * null when it is not under `directory` at all. What every menu marks.
 *
 * For a crumb's own menu this is the crumb — the menu is the crumb's parent,
 * and the crumb is the child of it on the way to the file. Inside a submenu
 * it keeps marking the way down, which is what the ellipsis's folded
 * ancestors need.
 *
 * @param {string} directory
 * @param {string|null} target
 * @returns {string|null}
 */
export function stepToward(directory, target) {
  if (target === null || target === "") {
    return null;
  }
  if (directory === "") {
    return target.split("/")[0] ?? null;
  }
  if (!target.startsWith(`${directory}/`)) {
    return null;
  }
  const rest = target.slice(directory.length + 1).split("/")[0];
  return rest ? `${directory}/${rest}` : null;
}

/**
 * The directory an entry lives in: `""` at the root.
 * @param {string} path
 * @returns {string}
 */
export function parentOf(path) {
  const slash = path.lastIndexOf("/");
  return slash < 0 ? "" : path.slice(0, slash);
}

/**
 * The last segment of a root-relative path.
 * @param {string} path
 * @returns {string}
 */
export function nameOf(path) {
  return path.split("/").pop() ?? path;
}
