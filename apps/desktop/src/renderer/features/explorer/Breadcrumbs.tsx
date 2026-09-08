import { Check, EllipsisVertical } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@renderer/components/ui/dropdown-menu";
import { cn } from "@renderer/lib/utils";
import { useExplorer, useTree } from "@renderer/state/explorer";
import type { DirEntry } from "@shared/ipc/explorer";

import { menuEntries, nameOf, stepToward, type Crumb } from "./crumbs";
import { EntryContextMenu, EntryMenuItems, useMenuFocusGuard } from "./EntryContextMenu";
import { renameEntry, requestAt, type EntryActionContext } from "./entry-actions";
import { FileIcon, FolderIcon } from "./icons";
import { InlineName } from "./InlineName";

/**
 * The file tab's breadcrumb: every crumb is a menu of its NEIGHBOURS.
 *
 * A crumb's menu is its parent directory's listing, so the first crumb drops
 * down the root's entries, a folder crumb drops down what sits beside that
 * folder, and the file crumb drops down its siblings — with the crumb itself
 * marked in each. The rule and the reason there is no crumb for the root are
 * in `crumbs.ts`. A folder inside a menu is a submenu of its own listing,
 * fetched when it is opened and kept in the explorer store beside the tree's
 * — the same cache, so a folder the tree already read costs the menu nothing.
 *
 * Right-click any crumb for the entry menu the tree's rows have; the file
 * crumb also carries a `⋯` that opens the same menu by click, because a
 * right-click is not a control anybody can see.
 *
 * The listings are the tree's (`useTree`), which is what makes this a view
 * over the same data rather than a second tree with a second idea of what
 * is on disk.
 */
export function Breadcrumbs({
  crumbs,
  ctx,
  activePath,
  onOpen,
  renaming,
  onRenamed,
  onRenameEnd,
}: {
  crumbs: Crumb[];
  ctx: EntryActionContext;
  /** The open file, marked in the menus. */
  activePath: string | null;
  onOpen: (path: string) => void;
  /** The file crumb draws an inline field while this is true. */
  renaming: boolean;
  onRenamed: (path: string) => void;
  onRenameEnd: () => void;
}) {
  return (
    <>
      {crumbs.map((crumb, index) => {
        const last = index === crumbs.length - 1;
        return (
          <span
            className={cn("flex min-w-0 items-center gap-1", last ? "shrink-0" : "shrink")}
            key={`${crumb.kind}-${crumb.path}-${index}`}
          >
            {index > 0 ? (
              <span className="shrink-0 text-muted-foreground/60" aria-hidden>
                ›
              </span>
            ) : null}
            {crumb.kind === "file" && renaming ? (
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
            ) : (
              <>
                <CrumbButton activePath={activePath} crumb={crumb} ctx={ctx} last={last} onOpen={onOpen} />
                {/*
                  The file's own actions, immediately after its name. The
                  same menu the right-click opens, drawn as a dropdown — one
                  table (`entry-menu.ts`), one set of actions, two doors.
                */}
                {crumb.kind === "file" ? <CrumbActions crumb={crumb} ctx={ctx} /> : null}
              </>
            )}
          </span>
        );
      })}
    </>
  );
}

function CrumbActions({ crumb, ctx }: { crumb: Crumb; ctx: EntryActionContext }) {
  const guard = useMenuFocusGuard(ctx);
  const entry = { path: crumb.path, kind: "file" as const, surface: "crumb" as const };
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
          <EllipsisVertical className="size-3.5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="w-56"
        data-entry-menu={entry.path}
        onCloseAutoFocus={guard.onCloseAutoFocus}
        sideOffset={6}
      >
        <EntryMenuItems ctx={guard.ctx} entry={entry} surface="dropdown" />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function CrumbButton({
  crumb,
  ctx,
  last,
  activePath,
  onOpen,
}: {
  crumb: Crumb;
  ctx: EntryActionContext;
  last: boolean;
  activePath: string | null;
  onOpen: (path: string) => void;
}) {
  const label = <span className="truncate">{crumb.label}</span>;
  const className = cn(
    "flex min-w-0 items-center gap-1 truncate rounded-sm px-0.5 outline-none transition-colors",
    last ? "max-w-[60vw] font-medium text-foreground" : "text-muted-foreground",
    "hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:text-foreground",
  );

  const trigger = (
    <DropdownMenuTrigger asChild>
      <button
        aria-label={`Browse ${crumb.kind === "ellipsis" ? crumb.title : crumb.label}`}
        className={className}
        data-crumb={crumb.kind}
        title={crumb.title}
        type="button"
      >
        {label}
      </button>
    </DropdownMenuTrigger>
  );

  // The ellipsis stands for several folders at once, so it names no entry
  // and has no entry menu; every other crumb names exactly one.
  const entry =
    crumb.kind === "ellipsis"
      ? null
      : {
          path: crumb.path,
          kind: crumb.kind === "file" ? ("file" as const) : ("directory" as const),
          surface: "crumb" as const,
        };

  return (
    <DropdownMenu modal={false}>
      {entry ? (
        <EntryContextMenu ctx={ctx} entry={entry}>
          {trigger}
        </EntryContextMenu>
      ) : (
        trigger
      )}
      <DropdownMenuContent align="start" className="w-max min-w-44 max-w-80" sideOffset={6}>
        {crumb.kind === "ellipsis" ? (
          crumb.hidden.map((folder) => (
            <DirectorySubMenu
              activePath={activePath}
              ctx={ctx}
              directory={folder.path}
              key={folder.path}
              label={folder.label}
              marked={false}
              onOpen={onOpen}
            />
          ))
        ) : (
          <DirectoryMenuItems activePath={activePath} ctx={ctx} directory={crumb.menu ?? ""} onOpen={onOpen} />
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * One directory's listing, read through the explorer store and fetched
 * when the store has not seen it. The directory's own row in the tree —
 * when it has one — fills the same slot, so the two never disagree.
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

function DirectoryMenuItems({
  directory,
  activePath,
  ctx,
  onOpen,
}: {
  directory: string;
  activePath: string | null;
  ctx: EntryActionContext;
  onOpen: (path: string) => void;
}) {
  const listing = useListing(ctx, directory);
  // The entry on the way to the open file — the file itself in its own
  // folder, the next folder down in any of its ancestors.
  const entries = useMemo(
    () => (listing ? menuEntries(listing, stepToward(directory, activePath)) : null),
    [listing, activePath, directory],
  );

  if (entries === null) {
    return (
      <DropdownMenuItem className="text-[13px] text-muted-foreground" disabled>
        Reading…
      </DropdownMenuItem>
    );
  }
  if (entries.length === 0) {
    return (
      <DropdownMenuItem className="text-[13px] text-muted-foreground" disabled>
        {directory === "" ? "Empty" : `${nameOf(directory)} is empty`}
      </DropdownMenuItem>
    );
  }
  return (
    <>
      {entries.map((entry) =>
        entry.kind === "directory" ? (
          <DirectorySubMenu
            activePath={activePath}
            ctx={ctx}
            directory={entry.path}
            key={entry.path}
            label={entry.name}
            marked={entry.current}
            onOpen={onOpen}
          />
        ) : (
          <DropdownMenuItem
            aria-current={entry.current ? "page" : undefined}
            className={cn("min-w-0 text-[13px]", entry.current && "bg-accent/60 font-medium")}
            data-active={entry.current || undefined}
            data-entry={entry.path}
            key={entry.path}
            onSelect={() => onOpen(entry.path)}
            title={entry.path}
          >
            <FileIcon className="size-3.5 shrink-0" path={entry.path} />
            <span className="min-w-0 flex-1 truncate">{entry.name}</span>
            {entry.current ? <Check className="size-3.5 shrink-0" /> : null}
          </DropdownMenuItem>
        ),
      )}
    </>
  );
}

/**
 * A folder inside a menu: a submenu of its listing, read when it opens.
 *
 * Radix mounts a submenu's content only while it is open, so the listing
 * hook inside `DirectoryMenuItems` runs on the first hover and not for
 * every folder a menu shows.
 */
function DirectorySubMenu({
  directory,
  label,
  marked,
  activePath,
  ctx,
  onOpen,
}: {
  directory: string;
  label: string;
  marked: boolean;
  activePath: string | null;
  ctx: EntryActionContext;
  onOpen: (path: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <DropdownMenuSub onOpenChange={setOpen} open={open}>
      <DropdownMenuSubTrigger
        aria-current={marked ? "page" : undefined}
        className={cn("min-w-0 text-[13px]", marked && "bg-accent/60 font-medium")}
        data-active={marked || undefined}
        data-entry={directory}
        title={directory}
      >
        <FolderIcon className="size-3.5 shrink-0" open={open} />
        <span className="min-w-0 flex-1 truncate">{label}</span>
      </DropdownMenuSubTrigger>
      <DropdownMenuSubContent className="max-h-80 w-max min-w-44 max-w-80 overflow-y-auto">
        <DirectoryMenuItems activePath={activePath} ctx={ctx} directory={directory} onOpen={onOpen} />
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
