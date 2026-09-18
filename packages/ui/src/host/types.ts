import type { DocumentDrafts, LiveTextDocument, LivePdfDocument } from './documents.js';
import type { PromptContextPort } from '@hardcore/core/prompt';
import type { FileActions, FileSource } from '../file-viewer/types.js';

/** Environmental effects are supplied by the app; shared UI never discovers a clipboard. */
export interface ClipboardPort {
  writeText(text: string): Promise<void>;
  readText(): Promise<string>;
  writeImage(image: Blob | Promise<Blob>): Promise<void>;
  writeContent?(content: { text?: string; image?: Blob | Promise<Blob> }): Promise<void>;
}
export type ViewerCommandReceipt =
  | { status: 'completed' | 'unavailable' | 'cancelled' }
  | { status: 'stale'; committed?: boolean }
  | { status: 'conflict' | 'failed'; message?: string };
/** A bound target belongs to exactly one mounted source/document generation. */
export interface ViewerCommandTarget {
  sourceId: string;
  path: string | null;
  generation: string;
  save(): Promise<ViewerCommandReceipt>;
  reload(): ViewerCommandReceipt;
  focus(): ViewerCommandReceipt;
}
export interface ViewerHost {
  files: FileSource;
  documents?: { drafts: DocumentDrafts; bind(target: LiveTextDocument): () => void };
  /** Optional URL of host-bundled PDF.js cmaps/, standard_fonts/, wasm/, and iccs/. */
  pdf?: { assetBaseUrl?: string; bind(target: LivePdfDocument): () => void };
  /** Optional per-view registration, never a global command bus. */
  commands?: { bind(target: ViewerCommandTarget): () => void };
  fileActions?: FileActions;
  clipboard: ClipboardPort;
  promptContext: PromptContextPort;
  navigation: { openFile(path: string, options?: { target: 'current' | 'new' }): void };
  environment: { colorScheme: 'light' | 'dark'; platform?: string };
  /** Publish state during host shutdown/page exit; this is never an implicit document save. */
  lifecycle?: { subscribeFlush(listener: () => void): () => void };
}
