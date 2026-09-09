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
  SquareTerminal,
  Trash2
} from "lucide-react";
import { Fragment, createElement, useMemo, useRef } from "react";

import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuShortcut,
  ContextMenuTrigger
} from "@/components/ui/context-menu";
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuShortcut
} from "@/components/ui/dropdown-menu";

import { ALL_ENTRY_CAPABILITIES, FIELD_ENTRY_ACTIONS, entryMenu } from "./entry-menu.js";

/**
 * The menu on a file or a folder — the tree's rows, the breadcrumb's crumbs,
 * and the empty space under the tree (which is the root). What is in it is
 * `entry-menu.js`; what it DOES is the host's, handed in as one `onAction`
 * callback, because "copy this path" means an IPC round trip in the desktop
 * app and a clipboard write in a browser tab.
 *
 * `EntryMenuItems` is exported on its own because the tree does not wrap every
 * row in a menu of its own: one menu over the whole list, aimed at whichever
 * row was clicked, is one Radix root instead of three hundred. It also draws
 * in a dropdown (`surface="dropdown"`) for the file crumb's `⋯` button, which
 * opens by click rather than by right-click: Radix's two menu primitives take
 * the same item props, so one table and one set of actions serve both doors.
 */

const SURFACES = {
  context: { Item: ContextMenuItem, Separator: ContextMenuSeparator, Shortcut: ContextMenuShortcut },
  dropdown: { Item: DropdownMenuItem, Separator: DropdownMenuSeparator, Shortcut: DropdownMenuShortcut }
};

/** @typedef {"context"|"dropdown"} EntryMenuSurface */

const ICONS = {
  open: Eye,
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
  trash: Trash2
};

/**
 * A menu whose item starts an inline field must not take the focus back.
 *
 * Radix returns focus to the trigger when a menu closes, and it does so after
 * the exit animation — by which time the rename field has mounted and focused
 * itself, so the return blurs it, and a blur is a commit. This wraps the
 * host's action handler to note that a field-starting item ran, and answers
 * the `onCloseAutoFocus` that skips the return exactly then.
 *
 * Keyed off the ACTION rather than off a pair of wrapped callbacks, so a host
 * that cannot rename at all (a browser tab) needs no callbacks to wrap.
 *
 * @param {(action: import("./entry-menu.js").EntryAction, entry: import("./entry-menu.js").MenuEntryTarget) => void} onAction
 */
export function useEntryMenuFocusGuard(onAction) {
  const editing = useRef(false);
  const handler = useRef(onAction);
  handler.current = onAction;
  return useMemo(
    () => ({
      onAction: (action, entry) => {
        if (FIELD_ENTRY_ACTIONS.has(action)) {
          editing.current = true;
        }
        handler.current(action, entry);
      },
      onCloseAutoFocus: (event) => {
        if (editing.current) {
          editing.current = false;
          event.preventDefault();
        }
      }
    }),
    []
  );
}

/**
 * @param {object} props
 * @param {import("./entry-menu.js").MenuEntryTarget} props.entry
 * @param {import("./entry-menu.js").Platform} props.platform
 * @param {ReadonlySet<import("./entry-menu.js").EntryAction>} [props.capabilities]
 * @param {(action: import("./entry-menu.js").EntryAction, entry: import("./entry-menu.js").MenuEntryTarget) => void} props.onAction
 * @param {EntryMenuSurface} [props.surface]
 */
export function EntryMenuItems({
  entry,
  platform,
  capabilities = ALL_ENTRY_CAPABILITIES,
  onAction,
  surface = "context"
}) {
  const sections = entryMenu(entry, platform, capabilities);
  const { Item, Separator, Shortcut } = SURFACES[surface];
  return (
    <>
      {sections.map((section, index) => (
        <Fragment key={index}>
          {index > 0 ? <Separator /> : null}
          {section.map((item) => (
            <Item
              className="text-[13px]"
              data-action={item.action}
              key={item.action}
              onSelect={() => onAction(item.action, entry)}
              variant={item.destructive ? "destructive" : "default"}
            >
              {createElement(ICONS[item.action], { className: "size-3.5" })}
              {item.label}
              {item.shortcut ? <Shortcut>{item.shortcut}</Shortcut> : null}
            </Item>
          ))}
        </Fragment>
      ))}
    </>
  );
}

/**
 * One element's own right-click menu — a crumb.
 *
 * A host with no actions to offer gets no menu at all rather than an empty
 * one: `entryMenu` filtered by an empty capability set is an empty list, and a
 * right-click that opens a blank popover is worse than a right-click that does
 * nothing.
 *
 * @param {object} props
 * @param {import("./entry-menu.js").MenuEntryTarget} props.entry
 * @param {import("./entry-menu.js").Platform} props.platform
 * @param {ReadonlySet<import("./entry-menu.js").EntryAction>} [props.capabilities]
 * @param {(action: import("./entry-menu.js").EntryAction, entry: import("./entry-menu.js").MenuEntryTarget) => void} props.onAction
 * @param {import("react").ReactNode} props.children
 */
export function EntryContextMenu({
  entry,
  platform,
  capabilities = ALL_ENTRY_CAPABILITIES,
  onAction,
  children
}) {
  const guard = useEntryMenuFocusGuard(onAction);
  if (entryMenu(entry, platform, capabilities).length === 0) {
    return children;
  }
  return (
    <ContextMenu modal={false}>
      <ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
      <ContextMenuContent
        className="w-56"
        data-entry-menu={entry.path}
        onCloseAutoFocus={guard.onCloseAutoFocus}
      >
        <EntryMenuItems
          capabilities={capabilities}
          entry={entry}
          onAction={guard.onAction}
          platform={platform}
        />
      </ContextMenuContent>
    </ContextMenu>
  );
}
