/**
 * This app's half of the file tree.
 *
 * The tree itself — its rows, its glyphs, its indentation, its expand and
 * collapse, its keyboard, its filter box and its entry menu — is
 * `cad-viewer/shell`, the same component the standalone CAD Viewer draws. What
 * differs is where a listing comes from and what an entry menu's items do, so
 * both are handed over as a source adapter, exactly the way the breadcrumb's
 * listings already were (`crumb-source.tsx`).
 *
 * Here that means main: `explorer.list` reads one directory at a time with
 * gitignore semantics and a watcher behind it, and the answers are kept in the
 * explorer store beside the breadcrumb's — the same cache, so a folder a menu
 * has read costs the tree nothing and the two never disagree about what is on
 * disk. The standalone viewer answers the same questions out of a catalog it
 * already holds (`catalogTreeSource.js`).
 */
import { ALL_ENTRY_CAPABILITIES, type FileTreeSource } from "cad-viewer/shell";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useExplorer, useTree } from "@renderer/state/explorer";

import {
  createEntry,
  performEntryAction,
  renameEntry,
  requestAt,
  trashEntry,
  type EntryActionContext,
} from "./entry-actions";

export function useExplorerTreeSource({
  ctx,
  projectName,
}: {
  ctx: EntryActionContext;
  /** Named in the tree's "… is empty" line. */
  projectName: string;
}): FileTreeSource {
  const { projectId, root } = ctx;
  const { open: expanded, listings } = useTree(root);
  const setTreeOpen = useExplorer((state) => state.setTreeOpen);
  const setTreeListing = useExplorer((state) => state.setTreeListing);

  const setExpanded = useCallback(
    (update: (current: ReadonlySet<string>) => ReadonlySet<string>) => setTreeOpen(root, update),
    [root, setTreeOpen],
  );

  /**
   * Read one directory's children.
   *
   * A promise chain rather than `async`/`await`: the state is set from a
   * callback, which is the shape that says "this is an answer arriving", and
   * the shape React's rules can see. The same code written with `await` reads
   * to a linter as a synchronous setState inside whichever effect called it.
   */
  const load = useCallback(
    (directory: string) => {
      void window.hardcore.explorer
        .list({ ...requestAt({ projectId, root }), path: directory })
        .then((entries) => setTreeListing(root, directory, entries))
        .catch(() => {});
    },
    [projectId, root, setTreeListing],
  );

  /**
   * A revision that moves only when THIS root's watcher fired.
   *
   * The store's `fsRevision` is bumped by every root's batch, and the tree
   * re-reads everything it has open when the number moves; a worktree's agent
   * writing a file must not cost the checkout's tree a listing per open
   * folder. A subscription rather than an effect over `fsRevision` because it
   * is a reaction to an event, and it has to judge `changedRoot` at the moment
   * the batch arrives.
   */
  const [revision, setRevision] = useState(0);
  useEffect(
    () =>
      useExplorer.subscribe((state, previous) => {
        if (state.fsRevision !== previous.fsRevision && state.changedRoot === root) {
          setRevision((current) => current + 1);
        }
      }),
    [root],
  );

  const paths = useCallback(
    () =>
      window.hardcore.explorer
        .paths({ ...requestAt({ projectId, root }), path: "" })
        .then((result) => result.paths)
        .catch(() => [] as string[]),
    [projectId, root],
  );

  const onAction = useCallback(
    (action: Parameters<typeof performEntryAction>[0], entry: Parameters<typeof performEntryAction>[1]) => {
      void performEntryAction(action, entry, ctx);
    },
    [ctx],
  );
  const rename = useCallback(
    (entry: Parameters<typeof renameEntry>[0], name: string) => renameEntry(entry, name, ctx),
    [ctx],
  );
  const create = useCallback(
    (directory: string, kind: "file" | "directory", name: string) => createEntry(directory, kind, name, ctx),
    [ctx],
  );
  const trash = useCallback((entry: Parameters<typeof trashEntry>[0]) => trashEntry(entry, ctx), [ctx]);

  return useMemo(
    () => ({
      rootName: projectName,
      expanded,
      setExpanded,
      listings,
      load,
      revision,
      paths,
      platform: ctx.platform,
      capabilities: ALL_ENTRY_CAPABILITIES,
      onAction,
      rename,
      create,
      trash,
    }),
    [
      projectName,
      expanded,
      setExpanded,
      listings,
      load,
      revision,
      paths,
      ctx.platform,
      onAction,
      rename,
      create,
      trash,
    ],
  );
}
