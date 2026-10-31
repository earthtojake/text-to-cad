/** Package-owned contracts for the shared navigation primitives. */
import type { ComponentType, ElementType, ReactNode } from "react";
import type { FileSource } from "../types.js";

/* -------------------------------------------------------------------- */
/* The file menu                                                         */
/* -------------------------------------------------------------------- */

/** What the ⋯ after the file's name can offer. */
export type EntryAction = "copy-path" | "reveal";
export type Platform = "darwin" | "win32" | "linux";
export type EntryMenuItem = { action: EntryAction; label: string };

export const ENTRY_ACTIONS: readonly EntryAction[];
/** The menu for the file on screen: the actions the host can perform, in a fixed order. */
export function entryMenu(platform: Platform, capabilities: ReadonlySet<EntryAction>, t?: (key: string) => string): EntryMenuItem[];
export function revealLabel(platform: Platform, t?: (key: string) => string): string;

/* -------------------------------------------------------------------- */
/* The explorer                                                          */
/* -------------------------------------------------------------------- */

/**
 * The file explorer the navbar's file name opens: one folder at a time from the open file's folder,
 * its subfolders opening inline (a double-click opens one in their place), a breadcrumb to climb (an
 * ellipsis for the folders above the crumbs that fit), and a search under the folder it is in. A
 * pick is `onOpen`.
 */
export const FolderExplorer: ComponentType<{
  source: Pick<FileSource, "list" | "search">;
  /** The open file, by its absolute path (a document with no file of its own: its id). */
  file: string;
  /** Where it starts: the open file's folder unless given (a model's: where the explorer was last, else home). */
  folder?: string | null;
  onOpen: (path: string) => void;
  /** The folder it is in, each time it changes (its first included). */
  onFolderChange?: (folder: string) => void;
}>;
/** The folders from the top of `path`'s filesystem down to it, `/`-separated. */
export function folderTrail(path: string): { name: string; path: string }[];
/** The folder holding `path`. */
export function parentFolder(path: string): string;

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

/**
 * The one navbar, over a file and over a host's home (with no file, history or Back to home). Left: the logo, which opens the app's menu
 * (`AppMenu`), Back and Forward where the host keeps the view's history (`history`), the open file's
 * name, with no glyph (the door to the name menu: Models and Files, where the host has them) and its ⋯. Right: `update`, `trailing` (the file's actions), then `actions`.
 */
export const ViewerNavbar: ComponentType<{
  /** The host's home, where it has one: the app menu's Back to home. */
  onHome?: () => void;
  /** The rest of the app's menu: the host's links and the person's settings. */
  menu?: { links?: import("../../host/types.js").ViewerLinks; appSettings?: readonly import("../types.js").AppSetting[]; colorScheme?: import("../types.js").ColorSchemeSetting; language?: import("../types.js").LanguageSetting; platform?: string } | null;
  /** The view's own history, where the host keeps one: Back and Forward, each disabled where there is nowhere to go. */
  history?: import("../types.js").ViewerHistory | null;
  /** The open file, by its absolute path. */
  file?: string | null;
  /** The document's name where its path does not give it (a model's). */
  name?: string;
  /** What the open document is: a model (built from code) or a file. Its glyph before the name, and the name menu's first tab. */
  kind?: "model" | "file";
  /** The name menu's Files: the explorer, rooted at `folder` where given (a model's: where it was last, else home). */
  explorer?: { source: Pick<FileSource, "list" | "search">; folder?: string | null; onOpen: (path: string) => void; onFolderChange?: (folder: string) => void } | null;
  /** The name menu's Recent: the host's library, in the explorer's style, a row opening its document. */
  recent?: { list(): Promise<readonly import("../types.js").RecentDocument[]>; onOpen: (path: string) => void } | null;
  fileMenu?: { platform: Platform; capabilities: ReadonlySet<EntryAction>; onAction: (action: EntryAction, path: string) => void } | null;
  trailing?: ReactNode;
  /** The host's update button, first among the controls, while its install is behind. */
  update?: ReactNode;
  /** The host's own actions (the web viewer's Export), last in the row. */
  actions?: ReactNode;
  className?: string;
}>;

/**
 * The app's menu, from the navbar's logo: Back to home (`onHome`), the
 * person's settings (`appSettings`), Send feedback, GitHub and Discord, then the version and who
 * made it. `trigger` is the button that opens it.
 */
export const AppMenu: ComponentType<{
  trigger: import("react").ReactElement;
  onHome?: () => void;
  links?: import("../../host/types.js").ViewerLinks;
  appSettings?: readonly import("../types.js").AppSetting[];
  colorScheme?: import("../types.js").ColorSchemeSetting;
  language?: import("../types.js").LanguageSetting;
  platform?: string;
}>;

/**
 * A file's icon. The nine formats the CAD Viewer renders get its own
 * per-format glyphs; everything else is one lucide table.
 */
export const FileIcon: ComponentType<{ path: string; className?: string; strokeWidth?: number }>;
export const FolderIcon: ComponentType<{ open: boolean; className?: string }>;
export const GitHubMark: ComponentType<{ className?: string }>;
export const DiscordMark: ComponentType<{ className?: string }>;
