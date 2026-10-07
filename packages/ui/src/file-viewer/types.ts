import type { ComponentType, ElementType, ReactNode } from "react";
import type { EntryAction, Platform } from "./navigation/index.js";
import type { ViewerHost } from "../host/types.js";

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export interface FileEntry { path: string; name: string; kind: "file" | "directory" }
export interface FileMetadata extends FileEntry {
  size: number;
  extension: string;
  mime?: string;
  /** A source hint; each registration remains responsible for matching. */
  mediaType?: string;
  revision?: string;
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
/** An on/off setting of the host's own, in a Settings section it names (the CAD apps' Analytics). */
export interface AppSetting {
  id: string;
  label: string;
  checked: boolean;
  /** Shown, not changeable: something outside the app decided it (the label says what). */
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
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
/**
 * The viewer's features a person can turn off in the app menu, as the host keeps
 * them: each is on unless the host says it is off.
 */
export interface ViewerFeatures {
  /** Quick Edit: the note to the agent at the viewport's top-right, and every way it opens. */
  quickEdit?: boolean;
}
export interface RendererViewProps {
  /** The host's notice (a question it asks once): the viewport's top-right once the file is on screen, Quick Edit under it. */
  notice?: ReactNode;
  /** The features the person has left on (in the app menu): what is off is not offered at all. */
  features?: ViewerFeatures;
  /** Optional host-owned controls inside the Display panel (the web's appearance). */
  displayActions?: ReactNode;
  onNavigationActionsChange?: (actions: readonly FileNavigationAction[]) => void;
  file: FileMetadata;
  source: FileSource;
  /**
   * The navbar's box for the renderer's own view controls, last at its right end (the CAD
   * viewer's Display and Preview, for a 3D view); null where no navbar is drawn, as while the
   * renderer shows its file fullscreen.
   */
  navbarSlot: HTMLElement | null;
  /**
   * The renderer shows its file fullscreen (the CAD viewer's Preview), or no longer does: the
   * navbar steps aside while it lasts.
   */
  onFullscreenChange: (fullscreen: boolean) => void;
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
  /** The file on screen, by its absolute path; null shows the host's home. */
  file: string | null;
  host: ViewerHost;
  renderers: readonly RendererRegistration[];
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
  /** Host controls inside the CAD Display panel. */
  displayActions?: ReactNode;
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
  /**
   * The host's Full size button, where the host shows the view small (inline in a conversation):
   * the last of the navbar's own controls, before the renderer's view controls.
   */
  fullSize?: ReactNode;
  /** The view's own history, where the host keeps one: Back and Forward, between the navbar's logo and the file's name. */
  history?: ViewerHistory;
  /** The features the person has left on (in the app menu), for every renderer (`RendererViewProps.features`). */
  features?: ViewerFeatures;
  /** The host's notice, shown at the viewport's top-right once the file is on screen (`RendererViewProps.notice`). */
  notice?: ReactNode;
  onError?: (error: Error) => void;
  presentation?: {
    /** The host's home, shown with no file: a page of its own, with no navbar over it (it holds the host's links itself). */
    home?: ReactNode;
    loading?: ReactNode;
    /** A file that will not open: `missing` when it does not exist. */
    error?: (failure: { message: string; missing: boolean }) => ReactNode;
  };
}
