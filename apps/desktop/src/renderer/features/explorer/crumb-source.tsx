/**
 * This app's half of the breadcrumb.
 *
 * The crumbs, their menus and their icons are `cad-viewer/shell` — the same
 * code the standalone CAD Viewer draws. The one thing the two hosts do not
 * agree on is where a directory listing comes from, and what an entry menu's
 * items DO, so both are handed over as a source adapter.
 *
 * Listings are the tree's (`useTree`), read one directory at a time over IPC
 * and kept in the explorer store beside the tree's own — the same cache, so a
 * folder the tree has already read costs a menu nothing, and the two never
 * disagree about what is on disk. The standalone viewer answers the same
 * question out of a catalog it already holds
 * (`apps/viewer/src/client/shell/catalogFileSource.js`).
 */
import {
  ALL_ENTRY_CAPABILITIES,
  EntryContextMenu,
  EntryMenuItems,
  InlineName,
  useEntryMenuFocusGuard,
  type CrumbSource,
  type EntryAction,
  type MenuEntryTarget,
} from "cad-viewer/shell";
import { Ellipsis } from "lucide-react";
import { useCallback, useEffect } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { useExplorer, useTree } from "@renderer/state/explorer";
import type { DirEntry } from "@shared/ipc/explorer";

import { performEntryAction, renameEntry, requestAt, type EntryActionContext } from "./entry-actions";

/** The one handler the shared menu calls: an item was chosen. */
type MenuAction = (action: EntryAction, entry: MenuEntryTarget) => void;

/**
 * One directory's listing, read through the explorer store and fetched when
 * the store has not seen it. The directory's own row in the tree — when it
 * has one — fills the same slot.
 *
 * A `DirEntry` already has the `{ path, name, kind }` the shared menu reads;
 * its other fields ride along and are ignored there.
 */
function useListing(ctx: Pick<EntryActionContext, "projectId" | "root">, directory: string): DirEntry[] | null {
  const { listings } = useTree(ctx.root);
  const setTreeListing = useExplorer((state) => state.setTreeListing);
  const listed = listings[directory];
  const { projectId, root } = ctx;
  useEffect(() => {
    if (listed !== undefined) {
      return;
    }
    let cancelled = false;
    void window.hardcore.explorer
      .list({ ...requestAt({ projectId, root }), path: directory })
      .then((entries) => {
        if (!cancelled) {
          setTreeListing(root, directory, entries);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTreeListing(root, directory, []);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [listed, directory, projectId, root, setTreeListing]);
  return listed ?? null;
}

/**
 * The file crumb's `⋯`: the menu the right-click opens, drawn as a dropdown —
 * one table (`cad-viewer/shell`'s `entry-menu.js`), one set of actions, two
 * doors, because a right-click is not a control anybody can see. The
 * standalone viewer draws the same button over the same table, minus the
 * items a browser tab cannot perform.
 */
function CrumbActions({
  path,
  onAction,
  ctx,
}: {
  path: string;
  onAction: MenuAction;
  ctx: EntryActionContext;
}) {
  const guard = useEntryMenuFocusGuard(onAction);
  const entry = { path, kind: "file" as const, surface: "crumb" as const };
  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button
          aria-label="File actions"
          className="flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-accent data-[state=open]:text-accent-foreground"
          data-testid="crumb-actions"
          title="File actions"
          type="button"
        >
          <Ellipsis className="size-3.5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="w-56"
        data-entry-menu={entry.path}
        onCloseAutoFocus={guard.onCloseAutoFocus}
        sideOffset={6}
      >
        <EntryMenuItems
          capabilities={ALL_ENTRY_CAPABILITIES}
          entry={entry}
          onAction={guard.onAction}
          platform={ctx.platform}
          surface="dropdown"
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * The adapter `<FileNavRow source={…}>` takes: the listings, plus the entry
 * menus that make a crumb behave like a row of the tree.
 *
 * Not memoised. The object is new on every render and that is fine — the
 * shared component calls `useListing` unconditionally, once per open menu, so
 * the hooks inside it run in the same order whatever closure carries them.
 */
export function useExplorerCrumbSource({
  ctx,
  renaming,
  onRenamed,
  onRenameEnd,
}: {
  ctx: EntryActionContext;
  /** The file crumb draws an inline field instead of its name while this is true. */
  renaming: boolean;
  onRenamed: (path: string) => void;
  onRenameEnd: () => void;
}): CrumbSource {
  /*
    Everything a crumb's menu offers, the three field-starting items included:
    a crumb is not a row, so `Rename` and the two `New …` go to the context,
    which draws a field over the crumb or asks the tree for one. The tree
    handles those itself and never forwards them.
  */
  const onAction = useCallback<MenuAction>(
    (action, entry) => void performEntryAction(action, entry, ctx),
    [ctx],
  );

  return {
    useListing: (directory) => useListing(ctx, directory),
    wrapCrumb: ({ crumb, children }) => (
      <EntryContextMenu
        capabilities={ALL_ENTRY_CAPABILITIES}
        entry={{
          path: crumb.path,
          kind: crumb.kind === "file" ? "file" : "directory",
          surface: "crumb",
        }}
        onAction={onAction}
        platform={ctx.platform}
      >
        {children}
      </EntryContextMenu>
    ),
    renderCrumbActions: ({ crumb }) => <CrumbActions ctx={ctx} onAction={onAction} path={crumb.path} />,
    renderRename: ({ crumb }) =>
      renaming ? (
        <InlineName
          className="max-w-64"
          initial={crumb.label}
          kind="file"
          label="Rename file"
          onCancel={onRenameEnd}
          onCommit={async (name) => {
            const renamed = await renameEntry({ path: crumb.path, kind: "file" }, name, ctx);
            if (renamed !== null) {
              onRenamed(renamed);
            }
            return renamed !== null;
          }}
        />
      ) : null,
  };
}
