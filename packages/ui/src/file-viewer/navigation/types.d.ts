/** Package-owned contracts for the shared navigation primitives. */
import type { ComponentType, ReactNode } from "react";

/* -------------------------------------------------------------------- */
/* The file menu                                                         */
/* -------------------------------------------------------------------- */

/** What a host can do with a document: its path copied, a link to its page copied, its file shown in the file manager, its page opened in the browser. */
export type EntryAction = "copy-path" | "copy-link" | "reveal" | "browser";
export type Platform = "darwin" | "win32" | "linux";
/** One item; Open in's say whether they can open now (`enabled`) and why not (`reason`, their hint). */
export type EntryMenuItem = { action: EntryAction; label: string; enabled?: boolean; reason?: string };

export const ENTRY_ACTIONS: readonly EntryAction[];
/** A home card's actions: Copy path, Copy link, then Reveal in the file manager, each where the host can do it. */
export function entryMenu(platform: Platform, capabilities: ReadonlySet<EntryAction>, t?: (key: string) => string): EntryMenuItem[];
export function revealLabel(platform: Platform, t?: (key: string) => string): string;
/** Open in's groups, in order; the drawing parts them with separators. */
export type OpenInGroup = "places" | "source" | "exports" | "default";
/** One place Open in opens the document in; an app's (`action: "app"`) names the file (`target`) and the app (`app`, or `"default"`). */
export type OpenInEntry = { action: EntryAction | "app"; label: string; enabled: boolean; reason?: string; group: OpenInGroup; target?: string; app?: string };
/**
 * The navbar's Open in: Browser and the file manager by its name (Finder, File Explorer, File manager), each where the
 * host can do it; then, from the host's answer (`files`), the source's apps, each present export's apps as "App (file)",
 * and Default app. What opens the source is disabled, with its reason, while it was moved or deleted; an app that
 * refuses its file (`refuses`: a KiCad older than the file's format) is disabled, saying so.
 */
export function openInMenu(platform: Platform, capabilities: ReadonlySet<EntryAction>, t?: (key: string, params?: Record<string, unknown>) => string,
  state?: { sourceMissing?: boolean; files?: import("../types.js").OpenInFiles | null }): OpenInEntry[];
export function fileManagerName(platform: Platform, t?: (key: string) => string): string;

/* -------------------------------------------------------------------- */
/* The project's list                                                    */
/* -------------------------------------------------------------------- */

/**
 * The Project tab the view's panel leads with where the document is in a project (`../projectPanel.js`): its models,
 * then its CAD files by folder below the project's, each a dense panel row of its glyph and name, the one on screen
 * marked; a press is `onOpen`. Nothing above the project, and no search.
 */
export const ProjectList: ComponentType<{
  project: Pick<import("../types.js").FileProject, "root" | "documents" | "truncated" | "missing" | "error">;
  /** The document on screen, by its path (a model's: its id). */
  current: string;
  onOpen: (document: import("../types.js").ProjectDocument) => void;
}>;
/** A project's documents as its list groups them: its models, then its files by their folder below the project's (`""`: its own). */
export function projectGroups<Row extends { path: string; kind?: string; folder?: string }>(documents: readonly Row[], root: string):
  { models: Row[]; folders: { folder: string; rows: Row[] }[] };

/** The one status screen, used by every full-area state in both apps: quiet, a 22rem column centred in the area. */
export const EmptyState: ComponentType<{
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}>;
/** A status screen's action: the panel's small quiet button. */
export const StatusAction: ComponentType<import("react").ButtonHTMLAttributes<HTMLButtonElement>>;

export function fuzzyMatch(
  needle: string,
  haystack: string,
): { score: number; indices: number[] } | null;

/**
 * The one navbar, over a file and over a host's home (with no file, history or Back to home). Left: the logo, which opens the app's menu
 * (`AppMenu`), Back and Forward where the host keeps the view's history (`history`), the project the document is in
 * (`project`: its name, muted, then a slash, which goes to the home at it), the open file's name, with no glyph, and its
 * ⋯ (Copy path, Open in, the host's own items: the viewer's Export, then for a document in no project Import its folder
 * as a project). Over a file with a panel, the panel's toggle comes first, before the logo. Right: `trailing` (the
 * file's actions), then `actions`, outermost. Back and Forward are a desktop row's alone: a phone's has no room for them.
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
  /** The project the document is in: its name before the document's, which goes to the home at it (`onOpen`). */
  project?: { name: string; onOpen: () => void } | null;
  /**
   * The ⋯ after the name: Copy path, then Open in (Browser, and the file manager by its name), each
   * where `capabilities` has it, then `items` (the host's own: the viewer's Export submenu), then Import its folder as
   * a project where `onImportFolder` is given. None where it would be empty.
   */
  fileMenu?: { platform: Platform; capabilities: ReadonlySet<EntryAction>; sourceMissing?: boolean;
    /** The host's apps for the document's files, asked each time the menu opens. */
    apps?: (options: { signal: AbortSignal }) => Promise<import("../types.js").OpenInFiles | null>;
    onAction: (action: EntryAction | "app", app?: { target: string; app: string }) => void; items?: ReactNode;
    /** Import its folder as a project: a document in no project. */
    onImportFolder?: (() => void) | null } | null;
  trailing?: ReactNode;
  /** The host's own actions (the CAD app's Full size, inline). */
  actions?: ReactNode;
  /**
   * The view's panel toggle (`../panelToggles.js`, said by its frame): the row's first control, before the logo, the
   * same neutral button open or shut (`aria-expanded` says which).
   */
  panels?: import("../panelToggles.js").PanelToggles | null;
  /** Over the home: the two places its controls go (its heading; the search and Import), on the grid's column (`../navbarSlots.js`). */
  homeSlots?: { left(element: HTMLElement | null): void; right(element: HTMLElement | null): void } | null;
  viewSlot?: ((element: HTMLElement | null) => void) | null;
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
 * A file's icon. The nine formats the viewer renders get its own
 * per-format glyphs; everything else is one lucide table.
 */
export const FileIcon: ComponentType<{ path: string; className?: string; strokeWidth?: number }>;
export const FolderIcon: ComponentType<{ open: boolean; className?: string }>;
export const GitHubMark: ComponentType<{ className?: string }>;
export const DiscordMark: ComponentType<{ className?: string }>;
