import { Check } from "lucide-react";
import { useMemo, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger
} from "@hardcore/ui/primitives/dropdown-menu";
import { cn } from "@hardcore/ui/utils";

import { menuEntries, nameOf, stepToward } from "./crumbs.js";
import { FileIcon, FolderIcon } from "./icons.jsx";

/**
 * The file tab's breadcrumb: every crumb is a menu of its NEIGHBOURS.
 *
 * A crumb's menu is its parent directory's listing, so the first crumb drops
 * down the root's entries, a folder crumb drops down what sits beside that
 * folder, and the file crumb drops down its siblings — with the crumb itself
 * marked in each. The rule and the reason there is no crumb for the root are
 * in `crumbs.js`. A folder inside a menu is a submenu of its own listing.
 *
 * Where those listings come from is the one thing the two apps do not share,
 * so it is a prop rather than an import. The desktop reads a directory at a
 * time over IPC and caches it in the explorer store beside the tree's; the
 * standalone viewer already holds the whole catalog and walks the directory
 * tree it builds from it (`catalogFileSource.js`). Both answer the same
 * question — "what is in this directory" — and neither knows about the other.
 *
 * @typedef {import("./crumbs.js").Crumb} Crumb
 * @typedef {import("./crumbs.js").ListingEntry} ListingEntry
 *
 * @typedef {object} CrumbSource
 * @property {(directory: string) => (readonly ListingEntry[]|null)} useListing
 *   One directory's entries, root-relative, or `null` while they are on their
 *   way. Called as a React hook — once per menu, unconditionally — so a source
 *   may hold state, and the object handed in must be STABLE across renders.
 *   Sorting is not its job: `menuEntries` orders and marks what comes back.
 * @property {(args: { crumb: Crumb, children: import("react").ReactNode }) => import("react").ReactNode} [wrapCrumb]
 *   Wraps one crumb's trigger — the host's right-click entry menu. Never
 *   called for the ellipsis, which names several folders and so names none.
 * @property {(args: { crumb: Crumb }) => import("react").ReactNode} [renderCrumbActions]
 *   Drawn immediately after the FILE crumb: the host's own `⋯`, because a
 *   right-click is not a control anybody can see.
 * @property {(args: { crumb: Crumb }) => import("react").ReactNode} [renderRename]
 *   Drawn INSTEAD of the file crumb while the host is renaming it — an inline
 *   field over the name. Returning null (or leaving it out) draws the crumb.
 *   The host owns the flag; there is no `renaming` prop here.
 */

/**
 * @param {object} props
 * @param {Crumb[]} props.crumbs
 * @param {CrumbSource} props.source
 * @param {string|null} props.activePath The open file, marked in the menus.
 * @param {(path: string, entry: ListingEntry) => void} props.onOpen
 */
export function Breadcrumbs({ crumbs, source, activePath, onOpen }) {
  return (
    <>
      {crumbs.map((crumb, index) => {
        const last = index === crumbs.length - 1;
        const rename = crumb.kind === "file" ? source.renderRename?.({ crumb }) : null;
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
            {rename ?? (
              <>
                <CrumbButton
                  activePath={activePath}
                  crumb={crumb}
                  last={last}
                  onOpen={onOpen}
                  source={source}
                />
                {/*
                  The file's own actions, immediately after its name — the
                  same menu the right-click opens, drawn as a dropdown. The
                  host supplies both, so one table of actions has two doors
                  and the shared chrome has none of its own.
                */}
                {crumb.kind === "file" ? source.renderCrumbActions?.({ crumb }) ?? null : null}
              </>
            )}
          </span>
        );
      })}
    </>
  );
}

function CrumbButton({ crumb, last, activePath, onOpen, source }) {
  const className = cn(
    "flex min-w-0 items-center gap-1 truncate rounded-sm px-0.5 outline-none transition-colors",
    last ? "max-w-[60vw] text-foreground" : "text-muted-foreground",
    "hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:text-foreground"
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
        <span className="truncate">{crumb.label}</span>
      </button>
    </DropdownMenuTrigger>
  );

  // The ellipsis stands for several folders at once, so it names no entry
  // and has no entry menu; every other crumb names exactly one.
  const wrapped =
    crumb.kind === "ellipsis"
      ? trigger
      : source.wrapCrumb?.({ crumb, children: trigger }) ?? trigger;

  return (
    <DropdownMenu modal={false}>
      {wrapped}
      <DropdownMenuContent align="start" className="w-max min-w-44 max-w-80" sideOffset={6}>
        {crumb.kind === "ellipsis" ? (
          crumb.hidden.map((folder) => (
            <DirectorySubMenu
              activePath={activePath}
              directory={folder.path}
              key={folder.path}
              label={folder.label}
              marked={false}
              onOpen={onOpen}
              source={source}
            />
          ))
        ) : (
          <DirectoryMenuItems
            activePath={activePath}
            directory={crumb.menu ?? ""}
            onOpen={onOpen}
            source={source}
          />
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function DirectoryMenuItems({ directory, activePath, onOpen, source }) {
  const listing = source.useListing(directory);
  // The entry on the way to the open file — the file itself in its own
  // folder, the next folder down in any of its ancestors.
  const entries = useMemo(
    () => (listing ? menuEntries(listing, stepToward(directory, activePath)) : null),
    [listing, activePath, directory]
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
            directory={entry.path}
            key={entry.path}
            label={entry.name}
            marked={entry.current}
            onOpen={onOpen}
            source={source}
          />
        ) : (
          <DropdownMenuItem
            aria-current={entry.current ? "page" : undefined}
            className={cn("min-w-0 text-[13px]", entry.current && "bg-accent/60 font-medium")}
            data-active={entry.current || undefined}
            data-entry={entry.path}
            key={entry.path}
            onSelect={() => onOpen(entry.path, entry)}
            title={entry.path}
          >
            <FileIcon className="size-3.5 shrink-0" path={entry.path} />
            <span className="min-w-0 flex-1 truncate">{entry.name}</span>
            {entry.current ? <Check className="size-3.5 shrink-0" /> : null}
          </DropdownMenuItem>
        )
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
function DirectorySubMenu({ directory, label, marked, activePath, onOpen, source }) {
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
        <DirectoryMenuItems
          activePath={activePath}
          directory={directory}
          onOpen={onOpen}
          source={source}
        />
      </DropdownMenuSubContent>
    </DropdownMenuSub>
  );
}
