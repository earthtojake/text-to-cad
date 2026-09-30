import type { DocumentDrafts, LiveTextDocument, LivePdfDocument } from './documents.js';
import type { PromptContextPort } from '@text-to-cad/core/prompt';
import type { FileActions, FileSource } from '../file-viewer/types.js';

/** Environmental effects are supplied by the app; shared UI never discovers a clipboard. */
export interface ClipboardPort {
  writeText(text: string): Promise<void>;
  readText(): Promise<string>;
  writeImage(image: Blob | Promise<Blob>): Promise<void>;
}
/**
 * What the navbar's right end links to — the running version (its release notes, and how to
 * update), the source and the community — and how a link is followed. Build it with
 * `viewerLinks` (`@text-to-cad/ui/links`), which fills in the defaults.
 */
export interface ViewerLinks {
  /** The version this host runs, as the navbar shows it (`0.7.4`). */
  version: string;
  /** That version's release notes. */
  release: string;
  github: string;
  discord: string;
  /** What updates the skills: a command for a terminal, and the same as a message for an agent. */
  install: { command: string; prompt: string };
  /**
   * The newest release, for a host that checks for one, and whether it is newer than `version`:
   * the version then reads "Update". Absent (or null), nothing was checked.
   */
  latest?: { version: string; url: string; newer: boolean } | null;
  /**
   * Follow a link. A host whose page cannot open one itself (a page in a sandboxed frame) supplies
   * this; without it a link opens the ordinary way, in a new tab.
   */
  open?(url: string): Promise<void>;
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
   *
   * `home` shows the host's home in this view: what it shows with no file open. A host with a
   * home offers it; the navbar's mark is then the way back to it from a file.
   */
  navigation: {
    openFile(path: string, options?: { target: 'current' | 'new'; panel?: string }): void;
    home?(): void;
  };
  /** The navbar's links: the version, GitHub and Discord. A host with none gets none. */
  links?: ViewerLinks;
  /**
   * `platform` names the keyboard's modifiers (⌘ on `darwin`, Ctrl elsewhere); `reducedMotion` is
   * the app's own motion setting, honoured beside the system's `prefers-reduced-motion`. `compact`
   * is a host showing the view small, inline in a conversation: a renderer draws the model and its
   * bottom action there, not its tools, its top-right bar or its view cube, and the view has no
   * navbar — its frame names what it shows.
   */
  environment: { colorScheme: 'light' | 'dark'; platform?: string; reducedMotion?: boolean; compact?: boolean };
}
