import type { HostFileRef } from '@emdash/core/primitives/path/api';
import {
  action,
  makeObservable,
  observable,
  reaction,
  runInAction,
  type IReactionDisposer,
} from 'mobx';
import {
  openFileStore,
  type ContentStatus,
  type OpenFileEntry,
  type OpenFileLease,
  type OpenFileStore,
} from '@core/features/editor/api/browser/open-file-store/open-file-store';
import {
  getFileKind,
  isMonacoBackedKind,
  isPreviewableKind,
} from '@core/features/editor/api/browser/renderers/fileKind';
import type {
  TabHandle,
  TabResource,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import type { ManagedFileKind } from '../../../../browser/renderers/types';

/** Whether the file is shown in Monaco (source) or its rendered preview. */
export type FileViewMode = 'source' | 'preview';

export interface FilePayload {
  path: string;
}

export type FileSelection = Readonly<{
  lineNumber: number;
  startColumn: number;
  endColumn: number;
}>;

export type FileSelectionRequest = Readonly<{
  id: number;
  selection: FileSelection;
}>;

const BUFFER = { kind: 'buffer' } as const;
const DISK = { kind: 'disk' } as const;

const READY: ContentStatus = { kind: 'ready' };
const LOADING: ContentStatus = { kind: 'loading' };
const UNAVAILABLE: ContentStatus = { kind: 'error', code: 'unavailable' };

export interface FileTabResourceOptions {
  /** Canonical identity; null only for unparseable paths. */
  ref?: HostFileRef | null;
  handle?: TabHandle;
  /** Test seam; production tabs use the app-global store. */
  store?: Pick<OpenFileStore, 'acquire'>;
  /**
   * Human-facing path for tooltips/toolbars. Files with no containing
   * workspace root show an absolute — host-prefixed when remote — path
   * (spec §5). Defaults to the tab path.
   */
  displayPath?: string;
  /** False when the file lives outside the workspace root (no tree reveal). */
  inWorkspace?: boolean;
}

/**
 * Domain resource for a single open file tab: identity (path + HostFileRef),
 * view mode, and selection requests. Text-backed files — inside or outside
 * any workspace root — hold ref-counted buffer+disk leases on the app-global
 * OpenFileStore for the tab's lifetime; all content state
 * (loading/ready/orphaned/error, dirty, conflicted) is read from the store's
 * entry, never duplicated here.
 */
export class FileTabResource implements TabResource {
  readonly path: string;
  readonly displayPath: string;
  readonly inWorkspace: boolean;
  readonly fileKind: Exclude<ManagedFileKind, 'too-large'>;
  readonly ref: HostFileRef | null;

  viewMode: FileViewMode;
  selectionRequest: FileSelectionRequest | null = null;
  /** Bumped on every buffer content change; touch before reading bufferText. */
  bufferVersion = 0;

  private nextSelectionRequestId = 1;
  private leases: OpenFileLease[] = [];
  private handleReaction: IReactionDisposer | null = null;
  private dirtyReaction: IReactionDisposer | null = null;
  private unsubscribeBufferChange: (() => void) | null = null;
  private readonly _store: Pick<OpenFileStore, 'acquire'>;
  private readonly _handle: TabHandle | null;

  constructor(payload: FilePayload, options: FileTabResourceOptions = {}) {
    const fileKind = getFileKind(payload.path);
    this.path = payload.path;
    this.displayPath = options.displayPath ?? payload.path;
    this.inWorkspace = options.inWorkspace ?? true;
    this.fileKind = fileKind;
    this.ref = options.ref ?? null;
    this.viewMode = isPreviewableKind(fileKind) ? 'preview' : 'source';

    this._store = options.store ?? openFileStore;
    this._handle = options.handle ?? null;

    makeObservable(this, {
      viewMode: observable,
      selectionRequest: observable.ref,
      bufferVersion: observable,
      setViewMode: action,
      requestSelection: action,
      consumeSelectionRequest: action,
    });

    if (this.usesOpenFileStore && this.ref) this.acquireContent(this.ref);
  }

  dispose(): void {
    this.unsubscribeBufferChange?.();
    this.unsubscribeBufferChange = null;
    this.handleReaction?.();
    this.handleReaction = null;
    this.dirtyReaction?.();
    this.dirtyReaction = null;
    for (const lease of this.leases) lease.release();
    this.leases = [];
  }

  onActivate?(): void {
    // No-op; file tabs don't need activation side-effects.
  }

  /** True for text-backed files whose content lives in OpenFileStore. */
  get usesOpenFileStore(): boolean {
    return isMonacoBackedKind(this.fileKind);
  }

  /** The shared open-file entry backing this tab, once leases are held. */
  get entry(): OpenFileEntry | undefined {
    return this.leases[0]?.entry;
  }

  /**
   * Content status the tab renders from. Non-text kinds (image,
   * binary-by-extension) load through their own preview pathways and report
   * ready; an unparseable path can never load and reports unavailable.
   */
  get contentStatus(): ContentStatus {
    if (!this.usesOpenFileStore) return READY;
    if (!this.ref) return UNAVAILABLE;
    return this.entry?.status ?? LOADING;
  }

  /** True when the buffer for this file has unsaved changes. */
  get isDirty(): boolean {
    return this.entry?.dirty ?? false;
  }

  /** Current buffer text; touch {@link bufferVersion} first in observers. */
  bufferText(): string {
    return this.entry?.handleFor(BUFFER)?.getText() ?? '';
  }

  /**
   * Restarts a failed load. Fresh leases are acquired before the old ones are
   * released: acquiring an errored facet restarts the load attempt, and the
   * overlapping interest prevents the store from tearing the entry down.
   */
  retryLoad(): void {
    if (!this.ref || this.leases.length === 0) return;
    const previous = this.leases;
    this.leases = [this._store.acquire(this.ref, BUFFER), this._store.acquire(this.ref, DISK)];
    for (const lease of previous) lease.release();
  }

  setViewMode(viewMode: FileViewMode): void {
    this.viewMode = viewMode;
  }

  requestSelection(selection: FileSelection): void {
    this.viewMode = 'source';
    this.selectionRequest = {
      id: this.nextSelectionRequestId,
      selection,
    };
    this.nextSelectionRequestId += 1;
  }

  consumeSelectionRequest(id: number): void {
    if (this.selectionRequest?.id === id) this.selectionRequest = null;
  }

  private acquireContent(ref: HostFileRef): void {
    this.leases = [this._store.acquire(ref, BUFFER), this._store.acquire(ref, DISK)];
    const entry = this.leases[0]!.entry;
    // The buffer handle appears asynchronously (and is replaced on re-key);
    // follow it so bufferVersion tracks content changes across handle swaps.
    this.handleReaction = reaction(
      () => entry.handleFor(BUFFER),
      (handle) => {
        this.unsubscribeBufferChange?.();
        this.unsubscribeBufferChange = handle?.onDidChange(() => this.bumpBufferVersion()) ?? null;
        if (handle) this.bumpBufferVersion();
      },
      { fireImmediately: true }
    );
    // Unsaved changes pin a preview tab so it can't be swept by the next preview.
    this.dirtyReaction = reaction(
      () => entry.dirty,
      (dirty) => {
        if (dirty) this._handle?.pin();
      }
    );
  }

  private bumpBufferVersion(): void {
    runInAction(() => {
      this.bufferVersion += 1;
    });
  }
}
