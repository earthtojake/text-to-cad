import type { ComponentType, ElementType, ReactNode } from "react";
import type { EntryAction, Platform } from "./navigation/index.js";
import type { ViewerHost } from "../host/types.js";
import type { LanguageSetting } from "../i18n/index.js";

export type { LanguageSetting };

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export interface FileEntry { path: string; name: string; kind: "file" | "directory" }
export interface FileMetadata extends FileEntry {
  /**
   * The on-disk file to browse from and act on (its Files, Copy path, Reveal); omitted it is
   * `path`. Null for a document with no file of its own (a model's, by its id): no file menu.
   */
  navigationPath?: string | null;
  /**
   * For a document with no file of its own (`navigationPath: null`), the file it is built from (a
   * model's script): what its file menu's Copy path and file manager act on. Its Files never start there.
   */
  sourceFile?: string;
  /**
   * The document's source (its file, a model's script) was moved or deleted: the file menu keeps
   * Copy path (where it was) and draws what opens the source disabled, saying why.
   */
  sourceMissing?: boolean;
  size: number;
  extension: string;
  mime?: string;
  /** A source hint; each registration remains responsible for matching. */
  mediaType?: string;
  revision?: string;
}
/** A document of a project, as the project lists it (`@cad/ui/library`'s rows): what `[` and `]` move through. */
export interface ProjectDocument {
  /** A file's absolute path, a model's id: what `navigation.openFile` opens. */
  path: string;
  name: string;
  /** `model` or `shape` for a document built from code; a file otherwise. */
  kind?: string;
  /** A file's folder (a model's script's), `/`-separated. */
  folder?: string;
  missing?: boolean;
}
/**
 * The project the document on screen is in (`FileViewerProps.project`): its name before the document's in the navbar,
 * which goes to the host's home at it (`onShow`), and its documents, in its order, the previous and next of which `[`
 * and `]` and the file menu show (`projectKeys.js`) -- null while they are read, with `truncated` where the host's walk
 * of its folder stopped early, `missing` where its folder is gone, `error` where they could not be read.
 */
export interface FileProject {
  id: string;
  name: string;
  /** Its folder, `/`-separated. */
  root: string;
  documents: readonly ProjectDocument[] | null;
  truncated?: boolean;
  missing?: boolean;
  error?: string | null;
  onShow(): void;
  /** Its page's own address, where the host has one (`navigation.hrefOf`): the navbar's project name is then a link. */
  href?: string | null;
}
/**
 * One app Open in offers for a file: its id (what `openApp` names) and its name, as drawn (a KiCad's says its
 * version). `refuses: "newer"`: it cannot open this file, which a newer version saved (a KiCad's), so it is drawn disabled.
 */
export interface OpenInApp { id: string; name: string; refuses?: 'newer' }
/**
 * One of a document's files Open in lists: `source` (a model's script, a file document's file) or
 * `export:<format>` (a file a model's last build wrote), its kind, its file's name, whether it is on
 * disk now, and the apps this computer has that take it (in the host's order).
 */
export interface OpenInTarget { target: string; kind: string; name: string; present: boolean; apps: readonly OpenInApp[]; default?: boolean }
/** A document's files and their apps (`GET /api/v1/local/open-in`'s answer, for a CAD host). */
export interface OpenInFiles { targets: readonly OpenInTarget[]; fileManager?: string }
export interface FileActions {
  platform?: Platform;
  /**
   * Each action the host can perform on a document, by its path (a model's: its id) and, where the
   * caller knows it, its document's id: `copy-path`, `copy-link` (its page with a fresh link, to the
   * clipboard), `reveal`, `browser`.
   */
  perform?: Partial<Record<EntryAction, (entry: Pick<FileEntry, "path" | "kind"> & { id?: string }) => void | Promise<void>>>;
  /**
   * Open in's apps, where the host can open a document's files in this computer's apps: the files
   * and their apps for the document on screen (asked as its file menu opens, never before; null or a
   * failure, and the menu is as without), and one opened in one of them -- `app` an app's id, or
   * `"default"`, the OS's own handler. Both or neither.
   */
  apps?: (entry: Pick<FileEntry, "path" | "kind">, options?: { signal?: AbortSignal }) => Promise<OpenInFiles | null>;
  openApp?: (entry: Pick<FileEntry, "path" | "kind">, target: string, app: string) => void | Promise<void>;
}
/** The files a view reads, by absolute path (`/`-separated): one file's metadata. */
export interface FileSource {
  /** Stable identity: what a document's key is named by. */
  id: string;
  stat: (path: string, options: { signal: AbortSignal }) => Promise<FileMetadata>;
}
export interface FileViewerState {
  /**
   * Each file's view under `JSON.stringify([file path, renderer id])`: what the host's tab store
   * holds (`@cad/ui/tab-store`), and where a renderer's `onStateChange` lands.
   */
  renderers?: Record<string, JsonValue>;
}
export interface PrepareContext {
  file: FileMetadata;
  source: FileSource;
  signal: AbortSignal;
  /** This same file was opened again by `reload`. */
  refresh?: boolean;
}
/**
 * A file's document, opened when the file is shown and again only on `reload`: a renderer follows
 * its file's changes itself (the CAD renderers read a live catalog entry), so the model on screen
 * is never taken down for an edit.
 */
export interface PreparedDocument<T> {
  data: T;
  dispose?: () => void;
}
/** Renderer-owned actions shown at the navbar's right. Never persisted. */
export interface FileNavigationAction {
  id: string;
  /** The accessible name. */
  label: string;
  /** The hover hint, when shorter than the label ("Snapshot" for "Take snapshot"); default the label. */
  hint?: string;
  icon: ElementType;
  disabled?: boolean;
  active?: boolean;
  onInvoke: () => void | Promise<void>;
}
/** An on/off setting of the host's own, in a Settings section it names (the CAD apps' Telemetry). */
export interface AppSetting {
  id: string;
  label: string;
  checked: boolean;
  /** What the setting means, in a hint beside its name (an info icon). */
  info?: string;
  /** Shown, not changeable: something outside the app decided it (the label says what). */
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}
/**
 * The person's colour scheme: System, Light or Dark, in the app menu. The host keeps
 * it and resolves System (the web against the OS, the CAD app against its host's theme).
 */
export interface ColorSchemeSetting {
  preference: "system" | "light" | "dark";
  onPreferenceChange: (preference: "system" | "light" | "dark") => void;
}
/**
 * A view's own history, where the host keeps one: what it showed, in order, as a browser keeps a
 * tab's. The navbar draws Back and Forward over it; a host whose page has a browser's history (the
 * web) hands none.
 */
export interface ViewerHistory {
  canGoBack: boolean;
  canGoForward: boolean;
  back(): void;
  forward(): void;
}
export interface RendererViewProps {
  /** The host's notice: the viewport's top-right once the file is on screen, Quick Edit under it. */
  notice?: ReactNode;
  onNavigationActionsChange?: (actions: readonly FileNavigationAction[]) => void;
  file: FileMetadata;
  source: FileSource;
  /**
   * The renderer's Preview is up (`true`) or has closed (`false`): FileViewer hides its navbar while
   * it is, Preview drawing its own bar in its place.
   */
  onPreviewChange?: (previewing: boolean) => void;
  onReady: (ready: boolean) => void;
  /**
   * Show another file, by its absolute path, in this view (a robot's mesh). Absent where the view
   * shows its file alone: a link to another file is plain text there.
   */
  onOpenFile?: (path: string) => void;
  appearance: { colorScheme: "light" | "dark" };
  /** The file's saved view as it stood when this renderer opened it; later saves do not come back. */
  state: JsonValue | undefined;
  onStateChange: (state: JsonValue) => void;
  reload: () => void;
}
export type FileRendererProps<T> = RendererViewProps & { data: T };
export interface FileRendererDefinition<T> {
  id: string;
  priority: number;
  matches: (file: FileMetadata) => boolean;
  fallback?: boolean;
  prepare: (context: PrepareContext) => Promise<PreparedDocument<T>>;
  load: () => Promise<{ default: ComponentType<FileRendererProps<T>> }>;
}
/** The typed payload is closed over by defineFileRenderer, never erased to `any`. */
export interface PreparedRenderer {
  Component: ComponentType<RendererViewProps>;
  dispose?: () => void;
}
export interface RendererRegistration {
  id: string;
  priority: number;
  matches: (file: FileMetadata) => boolean;
  fallback?: boolean;
  prepare: (context: PrepareContext) => Promise<PreparedRenderer>;
}
export interface FileViewerProps {
  /** Additive host actions at the navbar right (the CAD app's Full size), and persistent feedback below it. */
  navbarActions?: ReactNode;
  /**
   * The host's own items at the end of the file's ⋯ menu, after Copy path and Open in: menu items or
   * submenus (`DropdownMenuItem`, `DropdownMenuSub`), the viewer's Export. Over a document only.
   */
  fileMenuItems?: ReactNode;
  overlay?: ReactNode;
  /** The file on screen, by its absolute path; null shows the host's home. */
  file: string | null;
  /**
   * The file's name where the host knows it before the file is read (a CAD host's catalog row): the
   * navbar's name while the file opens. Without it a file is named by its path's last segment, and a
   * document named by its id is never named by the id: the name's place is empty until it is known.
   */
  name?: string;
  /**
   * The file's own path where the host knows it before the file is read (a document named by its id: the path its
   * catalog row gives, or the id of a model's): where the tab keeps its view, read for the panel's toggle until the
   * view is up.
   */
  filePath?: string | null;
  host: ViewerHost;
  renderers: readonly RendererRegistration[];
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
  /** The person's colour scheme, its row in the app menu (Settings' cog, in the sidebar's foot; the navbar's logo's where the host has no home). */
  colorScheme?: ColorSchemeSetting;
  /** The person's language, its row in the app menu (Automatic, or one they chose). */
  language?: LanguageSetting;
  /**
   * The person's on/off settings, in the app menu: the menu Settings' cog opens in the sidebar's foot (`PanelFoot.jsx`,
   * where the host's links, `host.links`, are icons), or, where the host has no home, the navbar's logo's.
   */
  appSettings?: readonly AppSetting[];
  /** The view's own history, where the host keeps one: Back and Forward after the navbar's logo, over a file and on the home. */
  history?: ViewerHistory;
  /**
   * The project the document on screen is in, where it is in one: its name before the document's in the navbar, and
   * its documents, the previous and next of which `[` and `]` and the file menu open through `navigation.openFile`.
   */
  project?: FileProject | null;
  /**
   * The search of every document, where the host has one (`@cad/ui`'s `search/DocumentSearch.tsx`, which `CadViewer`
   * mounts): ⌘K (Ctrl+K) anywhere outside Preview, and Search documents in a document's ⋯.
   */
  onSearch?: (() => void) | null;
  /**
   * Import its folder as a project, from the ⋯ of a document in no project, where the host can (`project` none): the
   * host's chooser, starting at the document's folder.
   */
  onImportFolder?: (() => void) | null;
  /** The host's notice, shown at the viewport's top-right once the file is on screen (`RendererViewProps.notice`). */
  notice?: ReactNode;
  /**
   * The chrome around the view: `"page"` (the default) draws the navbar over every file and over the
   * home; `"bare"` draws none, the view alone, for a host whose own frame is the navigation (the CAD
   * app's file handler). The renderer's own controls over the viewport are the same either way.
   */
  chrome?: "page" | "bare";
  /**
   * The viewer's layout pinned, for a viewer that is not the page's own (a picture drawn out of sight,
   * `OffscreenPicture.tsx`): neither measured nor said to the page, so its size never changes the page's.
   * Unset (the page's viewer): measured from its own width (`responsive.js`), and its root carries
   * `data-viewer-layout`, which the page's stylesheet reads (a phone's type a step up: `styles/globals.css`).
   */
  layout?: "desktop" | "mobile";
  onError?: (error: Error) => void;
  presentation?: {
    /**
     * The host's home, shown with no file: a page of its own under the navbar, which has there its sidebar's toggle
     * (which the home says, `panelToggles.js`), the logo, Back and Forward and the host's actions. The host's links
     * and the app's menu are the panel's foot's (`PanelFoot.jsx`), which the home's sidebar ends in.
     */
    home?: ReactNode;
    loading?: ReactNode;
    /**
     * A file that will not open: `missing` when it does not exist; `error`, what the source raised
     * (a host reads its own fields on it); `reload` rereads only this file.
     */
    error?: (failure: { message: string; missing: boolean; error?: unknown; reload?: () => void }) => ReactNode;
  };
}
