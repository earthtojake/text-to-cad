import type { DocumentDrafts, LiveTextDocument, LivePdfDocument } from './documents.js';
import type { PromptContextPort } from '@hardcore/core/prompt';
import type { FileActions, FileSource } from '../file-viewer/types.js';

/** Environmental effects are supplied by the app; shared UI never discovers a clipboard. */
export interface ClipboardPort {
  writeText(text: string): Promise<void>;
  readText(): Promise<string>;
  writeImage(image: Blob | Promise<Blob>): Promise<void>;
}
export interface ViewerHost {
  files: FileSource;
  documents?: { drafts: DocumentDrafts; bind(target: LiveTextDocument): () => void };
  /** Optional URL of host-bundled PDF.js cmaps/, standard_fonts/, wasm/, and iccs/. */
  pdf?: { assetBaseUrl?: string; bind(target: LivePdfDocument): () => void };
  fileActions?: FileActions;
  clipboard: ClipboardPort;
  promptContext: PromptContextPort;
  /**
   * Show a file: in this view, or in a new one where the host has more than one (`target`).
   * `panel` is the panel the file opens with, by id: the tree's, for a file picked in the tree,
   * so the tree stays up while a person walks it file by file. Without one, a file opened in
   * place or in a new view opens with its own default panel (`panels.js`: its controls, or
   * nothing), and a view that already shows the file keeps whatever it has open.
   */
  navigation: { openFile(path: string, options?: { target: 'current' | 'new'; panel?: string }): void };
  /**
   * `platform` names the keyboard's modifiers (⌘ on `darwin`, Ctrl elsewhere); `reducedMotion` is
   * the app's own motion setting, honoured beside the system's `prefers-reduced-motion`.
   */
  environment: { colorScheme: 'light' | 'dark'; platform?: string; reducedMotion?: boolean };
}
