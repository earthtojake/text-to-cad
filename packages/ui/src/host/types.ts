import type { PromptContextPort } from '@text-to-cad/core/prompt';
import type { FileActions, FileSource } from '../file-viewer/types.js';

/** Environmental effects are supplied by the app; shared UI never discovers a clipboard. */
export interface ClipboardPort {
  /**
   * `text` may still be on its way (a copied Quick Edit whose annotation is being saved): the write
   * starts inside the gesture that asked for it and takes the text when it arrives.
   */
  writeText(text: string | Promise<string>): Promise<void>;
  /** Read where the host exposes paste from its clipboard. */
  readText?(): Promise<string>;
  writeImage(image: Blob | Promise<Blob>): Promise<void>;
}
/**
 * A Quick Edit's .snapshot.json, made at Copy/Queue/Send: shared input, inline annotation
 * and measurements, with one job per drawn view (`cadgen snapshot --annotation PACKET --camera authored` draws each).
 * `create` returns compact inline JSON up to 1024 UTF-8 bytes, otherwise writes it and answers its path; `read` fetches it. `createHttpPromptFiles` (`@text-to-cad/core/client`) is the
 * viewer server's.
 */
export interface PromptFiles {
  create(request: {
    name: string; input: string;
    views: Array<Record<string, unknown> & { label: string }>;
    annotation: Record<string, unknown> | null;
    measurements?: Array<{ start: number[]; end: number[]; label: string; color: string }>;
  }): Promise<{ snapshot: string; inline?: never } | { inline: string; snapshot?: never }>;
  read(path: string): Promise<Blob>;
}
/**
 * What the app menu links to — the running version (its release notes), the source and the
 * community — and how a link is followed. Build it with
 * `viewerLinks` (`@text-to-cad/ui/links`), which fills in the defaults.
 */
export interface ViewerLinks {
  /**
   * The version this host runs, as the app menu shows it and a new issue names it: `0.7.4` for the
   * release's own build, `0.7.4-dev.<build>` for a custom build of it (`viewerLinks`' `build`).
   */
  version: string;
  /** The release notes of the release it is, or a custom build was built on. */
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
/** One export the page started: its request, the name it downloads as, and whether the browser was handed it. */
export interface ExportRecord { request: import('@text-to-cad/core/client').ExportRequest; filename: string; delivered: boolean }
/** The browser's own downloads. No picker, handle or server path crosses this port. */
export interface DownloadPort {
  /** Hands the browser a same-origin file URL to download as `filename`; where it goes is the browser's setting. */
  save(url: string, filename: string): void;
  restore?(): ExportRecord[];
  remember?(value: ExportRecord[]): void;
}
export interface ViewerHost {
  downloads?: DownloadPort;
  files: FileSource;
  fileActions?: FileActions;
  clipboard: ClipboardPort;
  promptContext: PromptContextPort;
  /** Makes a Quick Edit's views and annotation as one snapshot JSON file. Absent: a prompt carries none of them. */
  promptFiles?: PromptFiles;
  /**
   * Show a file, by its absolute path, in this view: a pick in the explorer, a renderer's link.
   * `home` shows the host's home in this view: its recent models, what it shows with no file. A
   * host with a home offers it, and the navbar's logo is the way to it from a file. A view that
   * shows one file alone (a host's file handler, whose own file tree is its navigation) offers
   * neither: it has no explorer, and a renderer's link to another file is plain text there.
   */
  navigation: {
    openFile?(path: string): void;
    home?(): void;
  };
  /** The navbar's links: the version, X, Discord, GitHub and new issues. A host with none gets none. */
  links?: ViewerLinks;
  /**
   * What the person used, for the host to count: its telemetry, never what they made. Absent, nothing is
   * counted. `quickEdit`: a Quick Edit reached its destination -- copied, queued or sent.
   */
  usage?: { used(feature: 'quickEdit'): void };
  /**
   * `platform` names the keyboard's modifiers (⌘ on `darwin`, Ctrl elsewhere); `reducedMotion` is
   * the app's own motion setting, honoured beside the system's `prefers-reduced-motion`. `compact`
   * is a view drawn with no chrome (the library's picture of a model, drawn out of sight): a
   * renderer draws the model alone — not its tools, its view's controls, its cube or its Quick
   * Edit — and the view has no navbar. `locale` is the language the view reads in, as the host
   * resolved it (`@text-to-cad/ui/i18n`'s `useLanguage`: the person's choice, else what the context
   * infers); one it does not speak, or none, reads English.
   */
  environment: { colorScheme: 'light' | 'dark'; locale?: string; platform?: string; reducedMotion?: boolean; compact?: boolean };
}
