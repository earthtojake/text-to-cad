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
 * (`project`: its name, muted, then a slash, which goes to the home at it: a link where it has an address; a folder tile
 * in a narrow row and on a phone), the open file's name, with no glyph, and its ⋯ (Copy path, Copy link, Open in new tab,
 * Open in, the host's own items: the viewer's Export, then Previous and Next in project, or for a document in no project
 * Import its folder as a project). Over a file with a panel, the panel's toggle comes first, before the logo. Right: `trailing` (the
 * file's actions), then `actions`, outermost. Back and Forward are a desktop row's alone: a phone's has no room for them.
 */
export const ViewerNavbar: ComponentType<{
  /** The host's home, where it has one: the app menu's Back to home. */
  onHome?: () => void;
  /** The rest of the app's menu: the host's links and the person's settings. */
  menu?: { links?: import("../../host/types.js").ViewerLinks; appSettings?: readonly import("../types.js").AppSetting[]; colorScheme?: import("../types.js").ColorSchemeSetting; language?: import("../types.js").LanguageSetting; platform?: string;
    /** The search of every document (⌘K), where the host has one: the menu's Search documents. */
    onSearch?: (() => void) | null } | null;
  /** The view's own history, where the host keeps one: Back and Forward, each disabled where there is nowhere to go. */
  history?: import("../types.js").ViewerHistory | null;
  /** The open file, by its absolute path. */
  file?: string | null;
  /** The document's name where its path does not give it (a model's). */
  name?: string;
  /**
   * The project the document is in: its name before the document's, which goes to the home at it (`onOpen`), a real
   * link where it has an address (`href`): a plain click is `onOpen`, a modified one the browser's.
   */
  project?: { name: string; href?: string | null; onOpen: () => void } | null;
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
    onImportFolder?: (() => void) | null;
    /** Open in new tab (or Open in browser): the document on screen beside this view, `label` the item's words. */
    beside?: { label: string; onSelect(): void } | null;
    /** Previous and Next in project, each null at its end: a document in a project of more than one. */
    neighbours?: { previous: (() => void) | null; next: (() => void) | null } | null } | null;
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
 * The app's menu, from the navbar's logo: Back to home (`onHome`), Search documents (`onSearch`), the
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
  /** The search of every document: Search documents, after Back to home, with its key. */
  onSearch?: (() => void) | null;
}>;

/**
 * A file's icon. The nine formats the viewer renders get its own
 * per-format glyphs; everything else is one lucide table.
 */
export const FileIcon: ComponentType<{ path: string; className?: string; strokeWidth?: number }>;
export const FolderIcon: ComponentType<{ open: boolean; className?: string }>;
export const GitHubMark: ComponentType<{ className?: string }>;
export const DiscordMark: ComponentType<{ className?: string }>;
