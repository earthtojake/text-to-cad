/**
 * What the context menu on a file or a folder offers, as data.
 *
 * One table for the tree's rows and the breadcrumb's crumbs, so a file
 * cannot have one menu in one place and another menu two hundred pixels
 * away. The component (`EntryContextMenu.tsx`) draws it; `entry-actions.ts`
 * performs it; the unit test reads it directly.
 *
 * The shape is the platform's: verbs first, the copies together, the edits
 * together, and the one destructive item alone at the bottom — the OS trash,
 * which is reversible, so there is no confirmation in front of it.
 */
import { isCadFile } from "@shared/cad-refs";

export type EntryAction =
  | "open"
  | "open-new-tab"
  | "open-default"
  | "open-with"
  | "reveal"
  | "copy-path"
  | "copy-relative-path"
  | "copy-reference"
  | "new-file"
  | "new-folder"
  | "open-terminal"
  | "rename"
  | "duplicate"
  | "trash";

export type EntryMenuItem = {
  action: EntryAction;
  label: string;
  destructive?: boolean;
  /** Printed at the right, the platform's way; the tree answers to it too. */
  shortcut?: string;
};

export type Platform = "darwin" | "win32" | "linux";

export type MenuEntryTarget = {
  /** Root-relative; `""` is the root itself, which has no rename and no trash. */
  path: string;
  kind: "file" | "directory";
};

/** What the OS calls its file browser. */
export function revealLabel(platform: Platform): string {
  switch (platform) {
    case "darwin":
      return "Reveal in Finder";
    case "win32":
      return "Show in Explorer";
    case "linux":
      return "Show in file manager";
  }
}

/** The menu, as sections; the component draws a separator between them. */
export function entryMenu(target: MenuEntryTarget, platform: Platform): EntryMenuItem[][] {
  const trashShortcut = platform === "darwin" ? "⌘⌫" : "Ctrl+Del";
  const rename: EntryMenuItem = { action: "rename", label: "Rename", shortcut: "F2" };
  const trash: EntryMenuItem = { action: "trash", label: "Move to Trash", destructive: true, shortcut: trashShortcut };
  const copies: EntryMenuItem[] = [
    { action: "copy-path", label: "Copy path" },
    { action: "copy-relative-path", label: "Copy relative path" },
  ];

  if (target.kind === "directory") {
    const root = target.path === "";
    return [
      [
        { action: "new-file", label: "New file" },
        { action: "new-folder", label: "New folder" },
        { action: "open-terminal", label: "Open in terminal" },
      ],
      [{ action: "reveal", label: revealLabel(platform) }],
      copies,
      ...(root ? [] : [[rename], [trash]]),
    ];
  }

  return [
    [
      { action: "open", label: "Open" },
      { action: "open-new-tab", label: "Open in new tab" },
    ],
    [
      { action: "open-default", label: "Open with default app" },
      { action: "open-with", label: "Open with…" },
      { action: "reveal", label: revealLabel(platform) },
    ],
    // A CAD file is something the composer can point at: its reference is
    // the token the agent reads (`@shared/cad-refs`).
    [...copies, ...(isCadFile(target.path) ? [{ action: "copy-reference" as const, label: "Copy reference" }] : [])],
    [rename, { action: "duplicate", label: "Duplicate" }],
    [trash],
  ];
}

/** Every action a menu can carry, flat — for a caller that wants to check one is offered. */
export function entryMenuActions(target: MenuEntryTarget, platform: Platform): EntryAction[] {
  return entryMenu(target, platform).flat().map((item) => item.action);
}
