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
  size: number;
  extension: string;
  mime?: string;
  /** A source hint; each registration remains responsible for matching. */
  mediaType?: string;
  revision?: string;
}
/** A document of the host's library, as the name menu's Recent lists it (`@text-to-cad/ui/library`'s rows). */
export interface RecentDocument {
  /** A file's absolute path, a model's id: what `navigation.openFile` opens. */
  path: string;
  name: string;
  /** `model` or `shape` for a document built from code; a file otherwise. */
  kind?: string;
  /** When a page last opened it, and when it was last updated, in seconds. */
  opened?: number | null;
  updated?: number | null;
  missing?: boolean;
}
export interface FileActions {
  platform?: Platform;
  perform?: Partial<Record<EntryAction, (entry: Pick<FileEntry, "path" | "kind">) => void | Promise<void>>>;
}
/**
 * The files a view reads, by absolute path (`/`-separated): one file's metadata, one folder's
 * subfolders and files, and a search under a folder that says when it stopped early.
 */
export interface FileSource {
  /** Stable identity: what a document's key is named by. */
  id: string;
  stat: (path: string, options: { signal: AbortSignal }) => Promise<FileMetadata>;
  list?: (directory: string, options: { signal: AbortSignal }) => Promise<readonly FileEntry[]>;
  search?: (directory: string, query: string, options: { signal: AbortSignal }) => Promise<{ paths: readonly string[]; truncated: boolean }>;
}
export interface FileViewerState {
  /**
   * Each file's view under `JSON.stringify([file path, renderer id])`: what the host's tab store
   * holds (`@text-to-cad/ui/tab-store`), and where a renderer's `onStateChange` lands.
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
 * The person's colour scheme: System, Light or Dark, in the app menu over every file. The host keeps
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
  /** Additive host actions at the navbar right, and persistent feedback below it. */
  navbarActions?: ReactNode;
  overlay?: ReactNode;
  /** The file on screen, by its absolute path; null shows the host's home. */
  file: string | null;
  host: ViewerHost;
  renderers: readonly RendererRegistration[];
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
  /** The person's colour scheme, its rows in the app menu the navbar's logo opens over every file. */
  colorScheme?: ColorSchemeSetting;
  /** The person's language, its row in the app menu over every file (Automatic, or one they chose). */
  language?: LanguageSetting;
  /**
   * The person's on/off settings, in the app menu the navbar's logo opens over every file, with
   * the host's links (`host.links`).
   */
  appSettings?: readonly AppSetting[];
  /**
   * The host's update button (`@text-to-cad/ui/update`'s `UpdateButton`), first among the navbar's
   * controls, while the host's install is behind; nothing otherwise.
   */
  update?: ReactNode;
  /** The view's own history, where the host keeps one: Back and Forward after the navbar's logo, over a file and on the home. */
  history?: ViewerHistory;
  /**
   * The host's library (a CAD host's Home), where it has one: the name menu's Models tab lists its
   * models, by last activity, and a row opens its model through `navigation.openFile`.
   */
  recent?: { list(): Promise<readonly RecentDocument[]> };
  /**
   * Where the name menu's Files starts for a document with no file of its own (a model's): the folder
   * the explorer was last in, else the person's home folder. Never the script it was built from. A
   * file's Files starts in its own folder.
   */
  explorerFolder?: string | null;
  /** The folder the explorer is in, each time it changes: the host keeps it for `explorerFolder`. */
  onExplorerFolderChange?(folder: string): void;
  /** The host's notice, shown at the viewport's top-right once the file is on screen (`RendererViewProps.notice`). */
  notice?: ReactNode;
  /**
   * The chrome around the view: `"page"` (the default) draws the navbar over every file and over the
   * home; `"bare"` draws none, the view alone, for a host whose own frame is the navigation (the CAD
   * app's file handler). The renderer's own controls over the viewport are the same either way.
   */
  chrome?: "page" | "bare";
  onError?: (error: Error) => void;
  presentation?: {
    /** The host's home, shown with no file: a page of its own under the navbar, which has only its logo's menu, Back and Forward, the update and the host's actions there. */
    home?: ReactNode;
    loading?: ReactNode;
    /**
     * A file that will not open: `missing` when it does not exist; `error`, what the source raised
     * (a host reads its own fields on it); `reload` rereads only this file.
     */
    error?: (failure: { message: string; missing: boolean; error?: unknown; reload?: () => void }) => ReactNode;
  };
}
