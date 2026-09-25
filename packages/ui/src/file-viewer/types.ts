import type { ResourceRef } from "@hardcore/core/prompt";
import type { ComponentType, ElementType, ReactNode } from "react";
import type { EntryAction, FilePanel, Platform } from "./navigation/index.js";
import type { ViewerHost } from "../host/types.js";

export type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };
export interface FileEntry { path: string; name: string; kind: "file" | "directory" }
export interface FileMetadata extends FileEntry {
  size: number;
  extension: string;
  mime?: string;
  modifiedAt?: number;
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
export interface ManagedFileAsset { url: string; bytes?: Uint8Array<ArrayBuffer>; mime?: string; resource?: ResourceRef; byteLength?: number; release: () => void }
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
  /** Keys encode [file path, renderer ID]; the host persists this state per source.id. */
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
export interface PreparedDocument<T> { data: T; text?: TextDocument; dispose?: () => void }
/** Renderer-owned actions shown before the common panel buttons. Never persisted. */
export interface FileNavigationAction {
  id: string;
  label: string;
  icon: ElementType;
  disabled?: boolean;
  active?: boolean;
  onInvoke: () => void | Promise<void>;
}
export interface RendererViewProps {
  /** Optional host-owned controls inside the Display popover. */
  displayActions?: ReactNode;
  /** Host-controlled presentation; disables editing/picking tools, not document state. */
  fullscreen?: boolean;
  /**
   * Enter or leave fullscreen. Given only to a renderer that declares `fullscreen` and only
   * by a host that has a fullscreen to offer, so its absence is the whole "no fullscreen here".
   */
  onFullscreenChange?: (fullscreen: boolean) => void;
  onNavigationActionsChange?: (actions: readonly FileNavigationAction[]) => void;
  file: FileMetadata;
  source: FileSource;
  document: DocumentSession | null;
  openPanel: string;
  /** Renderer status beside the filename; panel suspension preserves the open tab and width. */
  navigationStatusSlot?: HTMLElement | null;
  onPanelVisibilityChange?: (visible: boolean) => void;
  panelSlot: HTMLElement | null;
  onPanelOpen: (id: string) => void;
  onReady: (ready: boolean) => void;
  /** Preview modes can hide the common navigation and panel column. */
  onChromeVisibilityChange: (visible: boolean) => void;
  onOpenFile: (path: string, options?: { target: "current" | "new" }) => void;
  appearance: { colorScheme: "light" | "dark" };
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
  /** Offers fullscreen: the host's `onFullscreenChange` reaches this renderer and no other. */
  fullscreen?: boolean;
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
}
export interface RendererRegistration {
  id: string;
  priority: number;
  matches: (file: FileMetadata) => boolean;
  fallback?: boolean;
  fullscreen?: boolean;
  prepare: (context: PrepareContext) => Promise<PreparedRenderer>;
}
export interface FileViewerProps {
  /** The app owns fullscreen state and its surrounding chrome. */
  fullscreen?: boolean;
  /** The host's fullscreen, offered to a renderer that declares one; omitted, there is none. */
  onFullscreenChange?: (fullscreen: boolean) => void;
  file: string | FileMetadata | null;
  host: ViewerHost;
  renderers: readonly RendererRegistration[];
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
  leading?: ReactNode;
  /** Host content before renderer actions in the navbar. */
  navigationActions?: ReactNode;
  /** Host controls inside the CAD Display popover. */
  displayActions?: ReactNode;
  /** Override the selected path shown by breadcrumbs and tree, e.g. before a catalog resolves. */
  navigationPath?: string | null;
  /** Omit for automatic folding based on the available content width. */
  narrowCrumbs?: boolean;
  reveal?: { path: string; directory: boolean; nonce?: number } | null;
  onError?: (error: Error) => void;
  presentation?: { empty?: ReactNode; loading?: ReactNode; error?: (message: string) => ReactNode };
}
