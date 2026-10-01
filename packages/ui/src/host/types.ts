import type { DocumentDrafts, LiveTextDocument, LivePdfDocument } from './documents.js';
import type { PromptContextPort } from '@text-to-cad/core/prompt';
import type { FileActions, FileSource } from '../file-viewer/types.js';

/** Environmental effects are supplied by the app; shared UI never discovers a clipboard. */
export interface ClipboardPort {
  writeText(text: string): Promise<void>;
  readText(): Promise<string>;
  writeImage(image: Blob | Promise<Blob>): Promise<void>;
}
/** A file that failed to load or build, as the viewport's alert card shows it. */
export interface ViewerLoadFailure {
  /**
   * The failure's class: building (`compile`, `artifact`, `service`, `http`, `response`), reaching
   * the viewer (`network`), reading the file (`mesh`), a file with nothing in it (`empty`), or a
   * live edit that failed (`edit`). Absent for an alert a renderer raised without one.
   */
  kind?: string;
  /** The file as the renderer names it. */
  file?: string;
  title: string;
  message?: string;
  /** The loader's or interpreter's own words. */
  reason?: string;
  /** The complete diagnostic the card's Details shows. */
  details?: string;
  /** False when the previous version is still on screen. */
  blocking: boolean;
}
/**
 * One extra button on the card. `run` is called during the click; a string it resolves to is
 * shown as its outcome, and the card's actions stay disabled until it settles. `disabled` with a
 * `reason` is how an action says it cannot run now: the button stays focusable (`aria-disabled`)
 * and the reason is shown under it as its description — for a
 * prompt delivery, the host's destination state; the card re-asks when that state changes.
 */
export interface ViewerLoadFailureAction { label: string; disabled?: boolean; reason?: string; run(): void | Promise<string | void> }
/** What the host says instead of the card's default next step, and what it offers beside Try again. */
export interface ViewerLoadFailureRecovery { message?: string; recovery?: string; actions?: readonly ViewerLoadFailureAction[] }
export interface ViewerHost {
  /**
   * Optional: the host's words and actions for a load or build failure. Without it (or when it
   * returns nothing) the card keeps its default text, which names the served viewer's terminal.
   */
  loadFailures?: { recover(failure: ViewerLoadFailure): ViewerLoadFailureRecovery | null | undefined };
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
