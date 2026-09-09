import type { ComponentType, ReactNode } from "react";
import type { EntryAction, FilePanel, MenuEntryTarget, Platform } from "./navigation/index.js";

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
export interface ManagedFileAsset { url: string; mime?: string; release: () => void }
export type WriteResult =
  | { status: "saved"; document: TextDocument }
  | { status: "conflict"; message?: string }
  | { status: "error"; message: string };
export type ExternalEntryAction = Exclude<EntryAction, "open" | "rename" | "new-file" | "new-folder" | "trash">;
export interface FileActions {
  platform?: Platform;
  perform?: Partial<Record<ExternalEntryAction, (entry: MenuEntryTarget) => void | Promise<void>>>;
  rename?: (entry: MenuEntryTarget, name: string) => Promise<string | null>;
  create?: (directory: string, kind: "file" | "directory", name: string) => Promise<string | null>;
  trash?: (entry: MenuEntryTarget) => Promise<boolean>;
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
  writeText?: (path: string, options: { content: string; expectedRevision?: string; signal: AbortSignal }) => Promise<WriteResult>;
  subscribe?: (listener: (change: { sourceId: string; paths: readonly string[] }) => void) => () => void;
  actions?: FileActions;
}
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
  save: () => Promise<void>;
  reload: () => void;
  keepMine: () => void;
}
export interface PrepareContext { file: FileMetadata; source: FileSource; signal: AbortSignal }
export interface PreparedDocument<T> { data: T; text?: TextDocument; dispose?: () => void }
export interface FileActivity { loading: boolean; label?: string; title?: string }
export interface RendererViewProps {
  file: FileMetadata;
  source: FileSource;
  document: DocumentSession | null;
  openPanel: string;
  panelSlot: HTMLElement | null;
  onPanelOpen: (id: string) => void;
  onReady: (ready: boolean) => void;
  /** Preview modes can hide the common navigation and panel column. */
  onChromeVisibilityChange: (visible: boolean) => void;
  /** Renderer work that a host may present beside the filename. */
  onActivityChange: (activity: FileActivity | null) => void;
  onOpenFile: (path: string) => void;
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
  panels?: (context: { open: string; ready: boolean; file: FileMetadata }) => FilePanel[];
  prepare: (context: PrepareContext) => Promise<PreparedDocument<T>>;
  load: () => Promise<{ default: ComponentType<FileRendererProps<T>> }>;
}
/** The typed payload is closed over by defineFileRenderer, never erased to `any`. */
export interface PreparedRenderer {
  Component: ComponentType<RendererViewProps>;
  text?: TextDocument;
  dispose?: () => void;
}
export interface RendererRegistration {
  id: string;
  priority: number;
  matches: (file: FileMetadata) => boolean;
  fallback?: boolean;
  panels?: FileRendererDefinition<never>["panels"];
  prepare: (context: PrepareContext) => Promise<PreparedRenderer>;
}
export interface FileViewerProps {
  file: string | FileMetadata | null;
  source: FileSource;
  renderers: readonly RendererRegistration[];
  state: FileViewerState;
  onStateChange: (next: FileViewerState) => void;
  onOpenFile: (path: string, options?: { target: "current" | "new" }) => void;
  appearance?: { colorScheme: "light" | "dark" };
  leading?: ReactNode;
  /** Override the selected path shown by breadcrumbs and tree, e.g. before a catalog resolves. */
  navigationPath?: string | null;
  /** Omit for automatic folding based on the available content width. */
  narrowCrumbs?: boolean;
  reveal?: { path: string; directory: boolean; nonce?: number } | null;
  onError?: (error: Error) => void;
  presentation?: { empty?: ReactNode; treeActions?: ReactNode; loading?: ReactNode; error?: (message: string) => ReactNode; activity?: (activity: FileActivity | null) => ReactNode };
}
