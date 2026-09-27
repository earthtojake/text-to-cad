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

/** @typedef {"directory"|"file"} CrumbKind */

/**
 * @typedef {object} Crumb
 * @property {CrumbKind} kind
 * @property {string} label
 * @property {string} title The tooltip: the full segment.
 * @property {string} path Root-relative path of what the crumb names; never `""`.
 * @property {string} menu
 *   The directory whose listing the crumb's menu shows — its parent, so the
 *   menu is the crumb's neighbours. `""` is the root.
 * @property {string} current
 *   The entry the menu marks: the crumb itself. Equal to
 *   `stepToward(menu, path)`, which is what the component computes from the
 *   open file — this field is the rule written down.
 */

/**
 * Every segment is a crumb. A narrow (mobile) viewer shows the last one alone,
 * which is FileViewer's to choose.
 *
 * @param {object} input
 * @param {string|null} input.path The open file, root-relative; null for an empty tab.
 * @returns {Crumb[]}
 */
export function buildCrumbs({ path }) {
  const parts = path ? String(path).split("/").filter((part) => part !== "") : [];
  if (parts.length === 0) {
    return [];
  }
  const at = (index) => parts.slice(0, index + 1).join("/");
  return parts.map((label, index) => {
    const own = at(index);
    return {
      kind: index === parts.length - 1 ? "file" : "directory",
      label,
      title: label,
      path: own,
      menu: parentOf(own),
      current: own
    };
  });
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
 * and the crumb is the child of it on the way to the file. Inside a folder's
 * submenu it keeps marking the way down.
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
