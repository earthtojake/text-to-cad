import type { ComponentType, ElementType, ReactNode } from "react";
import type { EntryAction, FilePanel, Platform } from "./navigation/index.js";
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
export interface TextDocument {
  content: string;
  revision?: string;
  truncated?: boolean;
  readOnly?: boolean;
}
/** A source owns the URL; each successful read supplies a distinct release lease. */
export interface ManagedFileAsset { url: string; bytes?: Uint8Array<ArrayBuffer>; mime?: string; release: () => void }
export type FileFailureCode = "denied" | "not-found" | "already-exists" | "unsupported" | "conflict" | "error";
export type FileChange =
  | { kind: "content" | "metadata"; path: string; revision?: string }
  | { kind: "added" | "deleted"; path: string; entryKind: FileEntry["kind"] }
  | { kind: "moved"; from: string; to: string; entryKind: FileEntry["kind"] };
export interface FileChanges { sourceId: string; changes: readonly FileChange[] }
export type FileMutationResult =
  | { status: "committed"; path: string; change: FileChange }
  | { status: "cancelled" }
  | { status: "failed"; code: FileFailureCode; message: string };
export type WriteResult =
  | { status: "saved"; document: TextDocument }
  | { status: "conflict"; message?: string; actualRevision?: string }
  | { status: "cancelled" }
  | { status: "error"; code?: FileFailureCode; message: string };
export type ExternalEntryAction = Exclude<EntryAction, "open" | "rename" | "new-file" | "new-folder" | "trash" | "duplicate">;
export interface FileActions {
  platform?: Platform;
  perform?: Partial<Record<ExternalEntryAction, (entry: Pick<FileEntry, "path" | "kind">) => void | Promise<void>>>;
}
export interface FileSource {
  /** Stable workspace/root identity. Connection ports must never be used here. */
  id: string;
  rootName: string;
  /**
   * The name a copied reference gives `path`, one of this source's paths. Without it a
   * reference names the file by `path` itself, relative to this source's root; a root whose
   * relative paths mean nothing outside the viewer (a whole filesystem) gives the absolute path.
   */
  referencePath?: (path: string) => string;
  stat: (path: string, options: { signal: AbortSignal }) => Promise<FileMetadata>;
  list?: (directory: string, options: { signal: AbortSignal }) => Promise<readonly FileEntry[]>;
  paths?: (options: { signal: AbortSignal }) => Promise<readonly string[]>;
  readText?: (path: string, options: { signal: AbortSignal }) => Promise<TextDocument>;
  readAsset?: (path: string, options: { signal: AbortSignal }) => Promise<ManagedFileAsset>;
  /** Revision validation precedes an atomic replacement. Cancellation after dispatch cannot undo a commit. */
  writeText?: (path: string, options: { content: string; expectedRevision?: string; signal: AbortSignal }) => Promise<WriteResult>;
  rename?: (path: string, options: { name: string; signal: AbortSignal }) => Promise<FileMutationResult>;
  create?: (directory: string, options: { kind: FileEntry["kind"]; name: string; signal: AbortSignal }) => Promise<FileMutationResult>;
  duplicate?: (path: string, options: { signal: AbortSignal }) => Promise<FileMutationResult>;
  trash?: (path: string, options: { signal: AbortSignal }) => Promise<FileMutationResult>;
  subscribe?: (listener: (change: FileChanges) => void) => () => void;
}
export type DocumentSaveResult = WriteResult | { status: "unavailable" } | { status: "stale"; committed?: boolean };
export interface FileViewerState {
  panel: string | null;
  panelWidth: number;
  expandedDirectories?: readonly string[];
  /**
   * Each file's view under `JSON.stringify([file path, renderer id])`: what the host's tab store
   * holds for this root (`@text-to-cad/ui/tab-store`), and where a renderer's `onStateChange` lands.
   */
  renderers?: Record<string, JsonValue>;
}
export interface DocumentSession {
  /** Changes only for another source/file or an explicit/external reload. */
  key: string;
  value: string;
  revision?: string;
  readOnly: boolean;
  dirty: boolean;
  saving: boolean;
  stale: boolean;
  error: string | null;
  setValue: (value: string) => void;
  save: () => Promise<DocumentSaveResult>;
  reload: () => void;
  keepMine: () => void;
}
export interface PrepareContext {
  file: FileMetadata;
  source: FileSource;
  signal: AbortSignal;
  /** This same file was explicitly reloaded or invalidated by its source. */
  refresh?: boolean;
}
export interface PreparedDocument<T> {
  data: T;
  text?: TextDocument;
  dispose?: () => void;
  /**
   * The document follows its file by itself: a rewritten file reaches the open renderer as an update
   * (the CAD renderers read a live catalog entry), so the viewer keeps it open when the file's
   * content changes instead of opening it again, and the model on screen is never taken down for it.
   */
  live?: boolean;
}
/** Renderer-owned actions shown at the navbar's right, before any declared panel's toggle. Never persisted. */
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
  /** The Settings section it is listed in: Settings shows the same sections in the viewer and on the home. */
  section: string;
  label: string;
  checked: boolean;
  /** Shown, not changeable: something outside the app decided it (the label says what). */
  disabled?: boolean;
  onCheckedChange: (checked: boolean) => void;
}
export interface RendererViewProps {
  /** The host's notice (a question it asks once): the viewport's top-right once the file is on screen, Quick Edit under it. */
  notice?: ReactNode;
  /** Optional host-owned controls inside the Display panel (the web's appearance). */
  displayActions?: ReactNode;
  onNavigationActionsChange?: (actions: readonly FileNavigationAction[]) => void;
  file: FileMetadata;
  source: FileSource;
  document: DocumentSession | null;
  /**
   * The open panel id, for a renderer that declares `panels` of its own (the desktop markdown's
   * source view). The CAD renderers declare none and read none of `panelSlot` or `onPanelOpen`:
   * their controls are tool-stack panels, never the host's column. Their frame reads `openPanel`
   * only to put its tools out of sight while the explorer (`"tree"`) is open over them.
   */
  openPanel: string;
  /** The column's box for a declared `"slot"` panel to draw into. */
  panelSlot: HTMLElement | null;
  /**
   * The navbar's box for the renderer's own view controls, at its right end after the host's
   * Settings (the CAD viewer's Preview); null where no navbar is drawn.
   */
  navbarSlot: HTMLElement | null;
  /**
   * The renderer shows its file fullscreen (the CAD viewer's Preview), or no longer does: the
   * navbar, the explorer and any declared panel step aside while it lasts.
   */
  onFullscreenChange: (fullscreen: boolean) => void;
  onPanelOpen: (id: string) => void;
  onReady: (ready: boolean) => void;
  onOpenFile: (path: string, options?: { target: "current" | "new" }) => void;
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
  /** The nav row's panels for this file, which can depend on what `prepare` found (`data`). */
  panels?: (context: PanelContext & { data: T }) => FilePanel[];
  prepare: (context: PrepareContext) => Promise<PreparedDocument<T>>;
  load: () => Promise<{ default: ComponentType<FileRendererProps<T>> }>;
}
export interface PanelContext { open: string; ready: boolean; file: FileMetadata }
/** The typed payload is closed over by defineFileRenderer, never erased to `any`. */
export interface PreparedRenderer {
  Component: ComponentType<RendererViewProps>;
  /** The definition's panels over this document's prepared data. */
  panels?: (context: PanelContext) => FilePanel[];
  text?: TextDocument;
  dispose?: () => void;
  /** See `PreparedDocument.live`. */
  live?: boolean;
}
export interface RendererRegistration {
  id: string;
  priority: number;
  matches: (file: FileMetadata) => boolean;
  fallback?: boolean;
  prepare: (context: PrepareContext) => Promise<PreparedRenderer>;
}
export interface FileViewerProps {
  file: string | FileMetadata | null;
  host: ViewerHost;
  renderers: readonly RendererRegistration[];
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
  /** Host controls inside the CAD Display panel. */
  displayActions?: ReactNode;
  /**
   * The navbar's Settings, at its right end before the renderer's view controls, over every file:
   * the host composer's (`CadViewer`'s is the Settings popover the home has too).
   */
  settings?: ReactNode;
  /** The host's notice, shown at the viewport's top-right once the file is on screen (`RendererViewProps.notice`). */
  notice?: ReactNode;
  /**
   * Override the selected path the navbar names and the explorer marks, e.g. `null` while a host
   * catalog is still resolving the requested file. It does not change the requested document.
   */
  navigationPath?: string | null;
  reveal?: { path: string; directory: boolean; nonce?: number } | null;
  onError?: (error: Error) => void;
  presentation?: {
    empty?: ReactNode;
    /**
     * A host's home, shown for a tab with no file in place of `empty`: a page of its own, with no
     * navbar over it (it holds the host's links itself).
     */
    home?: ReactNode;
    loading?: ReactNode;
    error?: (message: string) => ReactNode;
  };
}
