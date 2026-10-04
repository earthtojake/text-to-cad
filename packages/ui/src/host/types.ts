import type { PromptContextPort } from '@text-to-cad/core/prompt';
import type { FileActions, FileSource } from '../file-viewer/types.js';

/** Environmental effects are supplied by the app; shared UI never discovers a clipboard. */
export interface ClipboardPort {
  /**
   * `text` may still be on its way (a copied Quick Edit whose sketch is being saved): the write
   * starts inside the gesture that asked for it and takes the text when it arrives.
   */
  writeText(text: string | Promise<string>): Promise<void>;
  readText(): Promise<string>;
  writeImage(image: Blob | Promise<Blob>): Promise<void>;
}
/**
 * Where a picture a prompt names by path is kept: a copied Quick Edit is text, so its sketch is
 * saved as a file on this machine and the text names it. `save` answers the file's absolute path.
 * `createHttpAttachmentStore` (`@text-to-cad/core/client`) is the viewer server's.
 */
export interface AttachmentStore {
  save(image: Blob, name: string): Promise<string>;
}
/**
 * What the app menu links to — the running version (its release notes), the source and the
 * community — and how a link is followed. Build it with
 * `viewerLinks` (`@text-to-cad/ui/links`), which fills in the defaults.
 */
export interface ViewerLinks {
  /** The version this host runs, as the app menu shows it (`0.7.4`). */
  version: string;
  /** That version's release notes. */
  release: string;
  x: string;
  github: string;
  discord: string;
  /**
   * Where a person opens a new issue (GitHub's `issues/new`): the app menu's Send feedback (over
   * every file and on the home) and an alert's Report Issue fill one in for them to finish, through GitHub's `title`, `labels`
   * and `body` parameters: a title begun ("Feedback: ", "Issue: ") and, for Report Issue, the
   * `bug` label. Empty: none of them is offered.
   */
  issues: string;
  /**
   * Follow a link. A host whose page cannot open one itself (a page in a sandboxed frame) supplies
   * this; without it a link opens the ordinary way, in a new tab.
   */
  open?(url: string): Promise<void>;
}
export interface ViewerHost {
  files: FileSource;
  fileActions?: FileActions;
  clipboard: ClipboardPort;
  promptContext: PromptContextPort;
  /** Saves a copied prompt's picture where the prompt can name it. Absent: a copied prompt names none. */
  attachments?: AttachmentStore;
  /**
   * Show a file, by its absolute path, in this view: a pick in the explorer, a renderer's link.
   * `home` shows the host's home in this view: its recent models, what it shows with no file. A
   * host with a home offers it, and the navbar's logo is the way to it from a file.
   */
  navigation: {
    openFile(path: string): void;
    home?(): void;
  };
  /** The navbar's links: the version, X, Discord, GitHub and new issues. A host with none gets none. */
  links?: ViewerLinks;
  /**
   * `platform` names the keyboard's modifiers (⌘ on `darwin`, Ctrl elsewhere); `reducedMotion` is
   * the app's own motion setting, honoured beside the system's `prefers-reduced-motion`. `compact`
   * is a view drawn with no chrome (the library's picture of a model, drawn out of sight): a
   * renderer draws the model alone — not its tools, its view's controls, its cube or its Quick
   * Edit — and the view has no navbar.
   */
  environment: { colorScheme: 'light' | 'dark'; platform?: string; reducedMotion?: boolean; compact?: boolean };
}
