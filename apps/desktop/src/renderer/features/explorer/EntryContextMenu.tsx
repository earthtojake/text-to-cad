import {
  AppWindow,
  Copy,
  CopyPlus,
  ExternalLink,
  Eye,
  FilePlus,
  FolderOpen,
  FolderPlus,
  Link,
  Pencil,
  SquarePlus,
  SquareTerminal,
  Trash2,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Fragment, createElement, useMemo, useRef } from "react";

import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuTrigger,
} from "@renderer/components/ui/context-menu";

import { performEntryAction, type EntryActionContext } from "./entry-actions";
import { entryMenu, type EntryAction, type MenuEntryTarget } from "./entry-menu";

/**
 * The right-click menu on a file or a folder — the tree's rows, the
 * breadcrumb's crumbs, and the empty space under the tree (which is the
 * root). What is in it is `entry-menu.ts`; what it does is
 * `entry-actions.ts`; this draws one from the other.
 *
 * `EntryMenuItems` is exported on its own because the tree does not wrap
 * every row in a menu of its own: one menu over the whole list, aimed at
 * whichever row was clicked, is one Radix root instead of three hundred.
 */

const ICONS: Record<EntryAction, LucideIcon> = {
  open: Eye,
  "open-new-tab": SquarePlus,
  "open-default": ExternalLink,
  "open-with": AppWindow,
  reveal: FolderOpen,
  "copy-path": Copy,
  "copy-relative-path": Copy,
  "copy-reference": Link,
  "new-file": FilePlus,
  "new-folder": FolderPlus,
  "open-terminal": SquareTerminal,
  rename: Pencil,
  duplicate: CopyPlus,
  trash: Trash2,
};

/**
 * A menu whose item starts an inline field must not take the focus back.
 *
 * Radix returns focus to the trigger when a menu closes, and it does so
 * after the exit animation — by which time the rename field has mounted
 * and focused itself, so the return blurs it, and a blur is a commit. This
 * wraps the two field-starting callbacks to note that one ran, and answers
 * the `onCloseAutoFocus` that skips the return exactly then.
 */
export function useMenuFocusGuard(ctx: EntryActionContext): {
  ctx: EntryActionContext;
  onCloseAutoFocus: (event: Event) => void;
} {
  const editing = useRef(false);
  return useMemo(
    () => ({
      ctx: {
        ...ctx,
        beginRename: (entry) => {
          editing.current = true;
          ctx.beginRename(entry);
        },
        beginCreate: (directory, kind) => {
          editing.current = true;
          ctx.beginCreate(directory, kind);
        },
      },
      onCloseAutoFocus: (event: Event) => {
        if (editing.current) {
          editing.current = false;
          event.preventDefault();
        }
      },
    }),
    [ctx],
  );
}

export function EntryMenuItems({ entry, ctx }: { entry: MenuEntryTarget; ctx: EntryActionContext }) {
  const sections = entryMenu(entry, ctx.platform);
  return (
    <>
      {sections.map((section, index) => (
        <Fragment key={index}>
          {index > 0 ? <ContextMenuSeparator /> : null}
          {section.map((item) => (
            <ContextMenuItem
              className="text-[13px]"
              data-action={item.action}
              key={item.action}
              onSelect={() => void performEntryAction(item.action, entry, ctx)}
              variant={item.destructive ? "destructive" : "default"}
            >
              {createElement(ICONS[item.action], { className: "size-3.5" })}
              {item.label}
              {item.shortcut ? <ContextMenuShortcut>{item.shortcut}</ContextMenuShortcut> : null}
            </ContextMenuItem>
          ))}
        </Fragment>
      ))}
    </>
  );
}

/** One element's own menu — a crumb. */
export function EntryContextMenu({
  entry,
  ctx,
  children,
}: {
  entry: MenuEntryTarget;
  ctx: EntryActionContext;
  children: React.ReactNode;
}) {
  const guard = useMenuFocusGuard(ctx);
  return (
    <ContextMenu modal={false}>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent className="w-56" data-entry-menu={entry.path} onCloseAutoFocus={guard.onCloseAutoFocus}>
        <EntryMenuItems ctx={guard.ctx} entry={entry} />
      </ContextMenuContent>
    </ContextMenu>
  );
}
