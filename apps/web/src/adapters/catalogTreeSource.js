/**
 * The shared file tree's source for a host that already holds every file it
 * can show: the standalone CAD Viewer.
 *
 * The desktop app's source reads a directory at a time over IPC, with
 * gitignore semantics and a watcher behind it. The viewer's backend has no
 * directory-listing route and needs none — one instance serves ONE directory
 * and the client polls its whole catalog, from which `workbench/sidebar.js`
 * builds a directory tree — so every answer here is a synchronous walk of a
 * structure already in memory: `load` is a no-op, and the corpus the filter
 * ranks is a flatten rather than a request.
 *
 * The consequence is the one place the two trees legitimately differ in
 * CONTENT: only CAD files are in the catalog, so the web tree shows the CAD
 * files the served directory holds and the directories containing them. That
 * is what this app can OPEN, which is the honest answer for a reader of a
 * served directory. Everything a person can see and do — the rows, the
 * glyphs, the indentation, the expand/collapse, the keyboard, the filter box —
 * is `FileTree.jsx` and is the same code in both apps.
 *
 * Relative imports and no `@/` alias, like `catalogFileSource.js` beside it,
 * so the pure half loads under bare `node --test`.
 */
import { useCallback, useMemo } from "react";

import { cadFileParamForEntry, sidebarLabelForEntry } from "../client/workbench/sidebar.js";

/**
 * Every directory in the catalog tree, as the tree's `listings` record.
 *
 * Built whole rather than a directory at a time because there is nothing to
 * defer: the catalog is already in memory and holds only the files this app
 * renders. A null tree is `{}`, which the tree reads as "still reading" — the
 * catalog's first poll, exactly.
 *
 * @param {object|null} directoryTree The root node from `buildSidebarDirectoryTree`.
 * @returns {Record<string, import("./FileTree.jsx").TreeEntry[]>}
 */
export function catalogTreeListings(directoryTree) {
  /** @type {Record<string, import("./FileTree.jsx").TreeEntry[]>} */
  const listings = {};
  if (!directoryTree) {
    return listings;
  }
  const walk = (node) => {
    listings[String(node.id || "")] = [
      ...(node.directories || []).map((child) => ({
        path: String(child.id || ""),
        name: String(child.name || ""),
        kind: "directory"
      })),
      ...(node.entries || []).map((entry) => ({
        path: cadFileParamForEntry(entry),
        name: sidebarLabelForEntry(entry),
        kind: "file"
      }))
    ];
    for (const child of node.directories || []) {
      walk(child);
    }
  };
  walk(directoryTree);
  return listings;
}

/**
 * Every file path in the catalog tree, flat: the corpus the filter ranks.
 *
 * @param {object|null} directoryTree
 * @returns {string[]}
 */
export function catalogTreePaths(directoryTree) {
  const listings = catalogTreeListings(directoryTree);
  return Object.values(listings)
    .flat()
    .filter((entry) => entry.kind === "file")
    .map((entry) => entry.path)
    .sort((left, right) => left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" }));
}

/**
 * The adapter `<FileTree source={…}>` takes, for the standalone viewer.
 *
 * Which folders are open is the CALLER's — the surface holds it, because it is
 * session state and the surface is the one writer of the session record. Every
 * function this hands over is stable, because the tree loads the root in an
 * effect keyed on `load`; `setExpanded` must be stable in the caller too.
 *
 * @param {object} options
 * @param {object|null} options.directoryTree
 * @param {string} options.rootName The served directory's name.
 * @param {ReadonlySet<string>} options.expanded
 * @param {(update: (current: ReadonlySet<string>) => ReadonlySet<string>) => void} options.setExpanded
 * @param {number} options.revision The catalog's revision; retires the filter corpus.
 * @param {import("./entry-menu.js").Platform} options.platform
 * @param {ReadonlySet<import("./entry-menu.js").EntryAction>} options.capabilities
 * @param {(action: import("./entry-menu.js").EntryAction, entry: import("./entry-menu.js").MenuEntryTarget) => void} options.onAction
 * @returns {import("./FileTree.jsx").FileTreeSource}
 */
export function useCatalogTreeSource({
  directoryTree,
  rootName,
  expanded,
  setExpanded,
  revision,
  platform,
  capabilities,
  onAction
}) {
  const listings = useMemo(() => catalogTreeListings(directoryTree), [directoryTree]);
  // Nothing to fetch: the catalog is the listing. The tree still calls this on
  // every expansion, which is what makes the same component work over a source
  // that does have to go and ask.
  const load = useCallback(() => {}, []);
  const pathsRef = useMemo(() => catalogTreePaths(directoryTree), [directoryTree]);
  const paths = useCallback(() => Promise.resolve(pathsRef), [pathsRef]);

  return useMemo(
    () => ({
      rootName,
      expanded,
      setExpanded,
      listings,
      load,
      revision,
      paths,
      platform,
      capabilities,
      onAction
    }),
    [rootName, expanded, setExpanded, listings, load, revision, paths, platform, capabilities, onAction]
  );
}
