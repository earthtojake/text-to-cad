/** Package-owned contracts for the shared navigation primitives. */
import type { ComponentType, ElementType, ReactNode } from "react";

/* -------------------------------------------------------------------- */
/* The entry menu                                                        */
/* -------------------------------------------------------------------- */

/** Everything the menu on a file or a folder can offer. */
export type EntryAction =
  | "open"
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

export type Platform = "darwin" | "win32" | "linux";

export type EntryMenuItem = {
  action: EntryAction;
  label: string;
  destructive?: boolean;
  shortcut?: string;
};

/** What a menu is aimed at. `""` is the root, which has no rename and no trash. */
export type MenuEntryTarget = {
  path: string;
  kind: "file" | "directory";
  /** The navbar names the open file, so its ⋯ menu has no `Open`. Default: the tree. */
  surface?: "tree" | "navbar";
};

/** Everything, for a host with a filesystem and an OS behind it. */
export const ALL_ENTRY_CAPABILITIES: ReadonlySet<EntryAction>;
/** What a browser tab can honestly do: the standalone viewer's set. */
export const WEB_ENTRY_CAPABILITIES: ReadonlySet<EntryAction>;
/** The three items that start an inline field instead of acting. */
export const FIELD_ENTRY_ACTIONS: ReadonlySet<EntryAction>;
export const ENTRY_ACTIONS: readonly EntryAction[];

export function entryMenu(
  target: MenuEntryTarget,
  platform: Platform,
  capabilities?: ReadonlySet<EntryAction>,
): EntryMenuItem[][];
export function entryMenuActions(
  target: MenuEntryTarget,
  platform: Platform,
  capabilities?: ReadonlySet<EntryAction>,
): EntryAction[];
export function revealLabel(platform: Platform): string;

/** One handler for every item: the host performs what the table offers. */
type EntryMenuAction = (action: EntryAction, entry: MenuEntryTarget) => void;

/**
 * Suppresses Radix's focus-return when the item that ran starts an inline
 * field — the return would blur the field, and a blur is a commit.
 */
export function useEntryMenuFocusGuard(onAction: EntryMenuAction): {
  onAction: EntryMenuAction;
  onCloseAutoFocus: (event: Event) => void;
};

export const EntryMenuItems: ComponentType<{
  entry: MenuEntryTarget;
  platform: Platform;
  capabilities?: ReadonlySet<EntryAction>;
  onAction: EntryMenuAction;
  /** Which Radix primitive draws the items: a right-click menu, or a dropdown. */
  surface?: "context" | "dropdown";
}>;

/* -------------------------------------------------------------------- */
/* The panel column and its list                                         */
/* -------------------------------------------------------------------- */

export type FilePanelContent = "tree" | "slot" | "body";

export type FilePanel = {
  id: string;
  label: string;
  icon: ElementType;
  content: FilePanelContent;
  defaultOpen?: boolean;
};

export const FILE_PANEL_TREE: string;
export function treePanel(open: string, options?: { empty?: boolean }): FilePanel;
export function resolveOpenPanel(panels: FilePanel[], panel: string | null): FilePanel | null;
export function nextOpenPanel(open: string, id: string): string;

export const PANEL_MIN_WIDTH: number;
export const PANEL_MAX_WIDTH: number;
export const PANEL_DEFAULT_WIDTH: number;
export function clampPanelWidth(width: number): number;

/**
 * The column a file's own declared panels open in, at the view's right: one border, one width,
 * one handle. The file tree is not one of them: it is the explorer (`FileExplorer`).
 */
export const FilePanelColumn: ComponentType<{
  mobile?: boolean;
  portalContainer?: HTMLElement | null;
  onDismiss?: () => void;
  hidden?: boolean;
  id: string;
  label: string;
  width: number;
  onWidthChange: (width: number) => void;
  onCollapse?: () => void;
  children: ReactNode;
}>;

/* -------------------------------------------------------------------- */
/* The file tree                                                         */
/* -------------------------------------------------------------------- */

/** One row's worth of a listing, root-relative. */
export type TreeEntry = {
  path: string;
  name: string;
  kind: "file" | "directory";
};

/** The one inline field the tree draws: a rename, or a new entry. */
export type TreeEditRequest =
  | { mode: "rename"; entry: MenuEntryTarget }
  | { mode: "create"; directory: string; kind: "file" | "directory" };
/** The same, asked for from outside; the nonce makes asking twice two requests. */
export type TreeEdit = TreeEditRequest & { nonce: number };

/**
 * Where the tree's listings come from and what its menu does — the one thing
 * the hosts do not share. A catalog host walks its catalog; a filesystem host
 * reads a folder at a time.
 */
export type FileTreeSource = {
  /** Named in the "… is empty" line. */
  rootName: string;
  expanded: ReadonlySet<string>;
  setExpanded: (update: (current: ReadonlySet<string>) => ReadonlySet<string>) => void;
  /** A directory absent from this map has not been read yet. */
  listings: Record<string, readonly TreeEntry[]>;
  /** Ask for one directory's entries; a host holding them already may no-op. */
  load: (directory: string) => void;
  /** Bumped when the filesystem moved on: re-reads what is open, retires the corpus. */
  revision: number;
  /** Every file path under the root, for the filter. Fetched on the first keystroke. */
  paths: () => Promise<readonly string[]>;
  platform: Platform;
  capabilities?: ReadonlySet<EntryAction>;
  /** Everything except the three that start a field, which the tree keeps. */
  onAction: EntryMenuAction;
  rename?: (entry: MenuEntryTarget, name: string) => Promise<string | null>;
  create?: (
    directory: string,
    kind: "file" | "directory",
    name: string,
  ) => Promise<string | null>;
  trash?: (entry: MenuEntryTarget) => Promise<boolean>;
};

export const FileTree: ComponentType<{
  source: FileTreeSource;
  /** The file the surface is showing, highlighted in the tree. */
  activePath: string | null;
  /** A path to expand to and select without opening it. */
  reveal?: { path: string; directory: boolean } | null;
  /** A rename or a create the navbar's menu asked for. */
  edit?: TreeEdit | null;
  onOpen: (path: string) => void;
}>;

/** The field a name is typed into, in place. */
export const InlineName: ComponentType<{
  initial: string;
  kind: "file" | "directory";
  placeholder?: string;
  className?: string;
  /** Resolve true to close the field; false keeps it up with the value intact. */
  onCommit: (name: string) => Promise<boolean>;
  onCancel: () => void;
  label?: string;
}>;

/** The one empty state, used by every pane in both apps. */
export const EmptyState: ComponentType<{
  icon: ElementType;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  /** `warn` is for a missing prerequisite, not an idle state. */
  tone?: "muted" | "warn";
}>;

export function fuzzyMatch(
  needle: string,
  haystack: string,
): { score: number; indices: number[] } | null;
export function fuzzyFilter(
  paths: readonly string[],
  query: string,
  limit?: number,
): { path: string; indices: number[] }[];

/**
 * The file explorer: a panel floating over the view's left, inset like the tool strip, above
 * everything under it; it never resizes the view. Below the viewer breakpoint, a sheet.
 */
export const FileExplorer: ComponentType<{
  label: string;
  width: number;
  onWidthChange: (width: number) => void;
  onCollapse?: () => void;
  mobile?: boolean;
  portalContainer?: HTMLElement | null;
  onDismiss?: () => void;
  children: ReactNode;
}>;

/** The open file as the navbar names it, with the explorer's menu for it. */
export type NavbarFile = {
  /** Root-relative. */
  path: string;
  capabilities: ReadonlySet<EntryAction>;
  platform: Platform;
  onAction: EntryMenuAction;
  /** While the host renames the file: a field over its name. */
  renaming?: { commit: (name: string) => Promise<boolean>; cancel: () => void } | null;
};

/**
 * The one navbar, over a file (a host's home has none). Left: the way back to the host's home, the
 * explorer's toggle, the open file's name and its ⋯. Right: `trailing` (the file's actions, its
 * panels' toggles), then the host's links.
 */
export const ViewerNavbar: ComponentType<{
  onBack?: () => void;
  explorer?: { open: boolean; onToggle: () => void } | null;
  file?: NavbarFile | null;
  /** No file is open: the name's place says "Select file", which opens the explorer. */
  selecting?: boolean;
  status?: ReactNode;
  trailing?: ReactNode;
  links?: import("../../host/types.js").ViewerLinks;
  clipboard: import("../../host/types.js").ClipboardPort;
  onError?: (error: Error) => void;
  className?: string;
}>;

/** The version, whose menu holds the release notes, GitHub and Discord, as the navbar's right end draws it. */
export const NavbarLinks: ComponentType<{
  links: import("../../host/types.js").ViewerLinks;
  clipboard: import("../../host/types.js").ClipboardPort;
  onError?: (error: Error) => void;
}>;

/** One panel's toggle in the navbar; `active` is its panel being open. */
export const PanelToggle: ComponentType<{
  icon: ElementType;
  label: string;
  active: boolean;
  onClick: () => void;
  id?: string;
  testId?: string;
}>;

/**
 * A file's icon. The nine formats the CAD Viewer renders get its own
 * per-format glyphs; everything else is one lucide table.
 */
export const FileIcon: ComponentType<{ path: string; className?: string }>;
export const FolderIcon: ComponentType<{ open: boolean; className?: string }>;
export const GitHubMark: ComponentType<{ className?: string }>;
export const DiscordMark: ComponentType<{ className?: string }>;
