/**
 * The breadcrumb's listings for a host that already holds every file it can
 * show: the standalone CAD Viewer.
 *
 * The viewer's backend has no directory-listing route and needs none. One
 * instance serves ONE directory and the client polls its whole catalog, from
 * which `workbench/sidebar.js` builds a directory tree — so "what is in this
 * directory" is a walk of a structure already in memory, answered
 * synchronously, with no request and no cache. A host that reads a directory
 * at a time over IPC (the desktop app) writes the other implementation of
 * this same adapter; neither knows the other exists.
 *
 * Only CAD files are in the catalog, so only CAD files are in these menus —
 * the breadcrumb lists what this app can open, not what is on disk.
 */
// Relative rather than through the `@/` alias: this module is pure, and its
// test runs under bare `node --test`, which resolves no bundler aliases.
import {
  cadFileParamForEntry,
  findSidebarDirectoryById,
  sidebarLabelForEntry
} from "../client/workbench/sidebar.js";

/**
 * One directory's entries in the crumb path space: root-relative paths, the
 * same strings `buildCrumbs` splits and the tree's directory ids extend.
 *
 * `null` — no tree yet — is "reading", which is what the catalog's first poll
 * looks like. An unknown directory id is an empty directory, not a missing
 * one: a menu that says "empty" is honest about a folder whose files have
 * been deleted since the tree was built.
 *
 * @param {object|null} directoryTree The root node from `buildSidebarDirectoryTree`.
 * @param {string} directory Root-relative directory id; `""` is the root.
 * @returns {import("@hardcore/ui/navigation").ListingEntry[]|null}
 */
export function catalogDirectoryListing(directoryTree, directory) {
  if (!directoryTree) {
    return null;
  }
  const node = findSidebarDirectoryById(directoryTree, directory);
  if (!node) {
    return [];
  }
  return [
    ...(node.directories || []).map((child) => ({
      path: String(child.id || ""),
      name: String(child.name || ""),
      kind: "directory"
    })),
    ...(node.entries || []).map((entry) => ({
      path: cadFileParamForEntry(entry),
      name: sidebarLabelForEntry(entry),
      kind: "file",
      // The catalog entry itself, handed back through `onOpen` — the standalone
      // selects by the entry's key, and looking one up again by path would be a
      // second answer to a question this already answered.
      value: entry
    }))
  ];
}

/**
 * The adapter `<Breadcrumbs source={…}>` takes.
 *
 * `useListing` is named as a hook because that is where it is called, and it
 * must obey the rules of one: the object is passed whole to `Breadcrumbs`, so
 * build it with `useMemo` on the tree and never swap in a different SHAPE of
 * source between renders. This one holds no state, so a new object with the
 * same behaviour is harmless — the memo is about not re-rendering every menu.
 *
 * @param {object} options
 * @param {object|null} options.directoryTree
 * @param {import("@hardcore/ui/navigation").CrumbSource} [options.slots]
 *   The host's own crumb menus (`wrapCrumb`, `renderCrumbActions`,
 *   `renderRename`), merged in so a caller builds one object rather than two.
 * @returns {import("@hardcore/ui/navigation").CrumbSource}
 */
export function createCatalogFileSource({ directoryTree, slots = {} }) {
  return {
    ...slots,
    useListing: (directory) => catalogDirectoryListing(directoryTree, directory)
  };
}
