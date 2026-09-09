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
  /** A crumb names the open file, so its menu has no `Open`. Default: the tree. */
  surface?: "tree" | "crumb";
};

/** Everything, for a host with a filesystem and an OS behind it: this app. */
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

/** One element's own right-click menu — a crumb. */
export const EntryContextMenu: ComponentType<{
  entry: MenuEntryTarget;
  platform: Platform;
  capabilities?: ReadonlySet<EntryAction>;
  onAction: EntryMenuAction;
  children: ReactNode;
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
export const SOURCE_PANEL: string;
export const CAD_PANEL: { readonly theme: string; readonly fileSheet: string };

/** The CAD surface's own two panels — both apps draw them. */
export function cadPanels(ready: boolean): FilePanel[];
/** The desktop's markdown source view, declared in the same vocabulary. */
export function markdownPanels(open: string): FilePanel[];
export function treePanel(open: string): FilePanel;
export function panelsFor(declared: FilePanel[], open: string): FilePanel[];
export function resolveOpenPanel(panels: FilePanel[], panel: string | null): FilePanel | null;
export function nextOpenPanel(open: string, id: string): string;
/** What the open panel becomes when the CAD surface reports one of its own. */
export function panelClosedBy(open: boolean, current: string, id: string): string;

export const PANEL_MIN_WIDTH: number;
export const PANEL_MAX_WIDTH: number;
export const PANEL_DEFAULT_WIDTH: number;
export function clampPanelWidth(width: number): number;

/** The one frame every panel is drawn in: one border, one width, one handle. */
export const FilePanelColumn: ComponentType<{
  id: string;
  label: string;
  width: number;
  onWidthChange: (width: number) => void;
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
 * the two hosts do not share. This app's is `features/explorer/tree-source.ts`;
 * the standalone viewer's walks its catalog.
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
  headerActions?: ReactNode;
  /** The file the surface is showing, highlighted in the tree. */
  activePath: string | null;
  /** A path to expand to and select without opening it. */
  reveal?: { path: string; directory: boolean } | null;
  /** A rename or a create the breadcrumb asked for. */
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

export type CrumbKind = "directory" | "file" | "ellipsis";

/** One crumb: a path segment BELOW the root, and the directory its menu lists. */
export type Crumb = {
  kind: CrumbKind;
  label: string;
  title: string;
  path: string;
  /** The crumb's PARENT — the menu is its neighbours. Null only for the ellipsis. */
  menu: string | null;
  current: string | null;
  hidden: { label: string; path: string }[];
};

/** One row of a crumb's menu, in the crumb path space. */
export type ListingEntry = {
  path: string;
  name: string;
  kind: "file" | "directory";
  /** The host's own payload, handed back on open. */
  value?: unknown;
};

/**
 * Where the breadcrumb's listings and entry menus come from — the one thing
 * the two hosts do not share. This app's is
 * `features/explorer/crumb-source.tsx`.
 */
export type CrumbSource = {
  /**
   * One directory's entries, or null while they are on their way. Called as
   * a React hook, unconditionally, once per open menu.
   */
  useListing: (directory: string) => readonly ListingEntry[] | null;
  /** Wraps a crumb's trigger — the right-click entry menu. Never the ellipsis. */
  wrapCrumb?: (args: { crumb: Crumb; children: ReactNode }) => ReactNode;
  /** Drawn after the FILE crumb: the `⋯` that opens the same menu by click. */
  renderCrumbActions?: (args: { crumb: Crumb }) => ReactNode;
  /** Drawn INSTEAD of the file crumb while the host is renaming it; null draws the crumb. */
  renderRename?: (args: { crumb: Crumb }) => ReactNode;
};

export function buildCrumbs(input: { path: string | null; narrow: boolean }): Crumb[];

/** The worktree a file is in, as a label rather than a crumb; null in the project. */
export function worktreeMark(root: string | null): { label: string; title: string } | null;

/** The directory an entry lives in: `""` at the root. */
export function parentOf(path: string): string;

export const Breadcrumbs: ComponentType<{
  crumbs: Crumb[];
  source: CrumbSource;
  activePath: string | null;
  onOpen: (path: string, entry: ListingEntry) => void;
}>;

/**
 * The row above a file: the breadcrumb, then whatever the host hangs off the
 * ends. `leading` sits inside the breadcrumb's overflow box and truncates
 * with it; `status` follows the last crumb; `trailing` is the right end and
 * never shrinks.
 */
export const FileNavRow: ComponentType<{
  crumbs: Crumb[];
  source: CrumbSource;
  activePath: string | null;
  onOpen: (path: string, entry: ListingEntry) => void;
  leading?: ReactNode;
  status?: ReactNode;
  trailing?: ReactNode;
  className?: string;
}>;

/** One panel's toggle at the end of the nav row; `active` is its panel being open. */
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

/** An element's width through a `ResizeObserver`; `0` until first measured. */
export function useElementWidth(): [(element: HTMLElement | null) => void, number];
