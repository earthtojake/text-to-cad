import type { GitChangeStatus, GitFilePath, GitObjectRef } from '@emdash/core/runtimes/git/api';
import { action, makeObservable, observable } from 'mobx';
import { getFileKind } from '@core/features/editor/api/browser/renderers/fileKind';
import type { ActiveFile } from '@core/features/tasks/contributions/mementos';
import type {
  TabHandle,
  TabResource,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import type { DiffTabManager } from './diff-tab-manager';

export type DiffViewMode = 'diff' | 'preview';
export type DiffPreviewKind = 'markdown' | 'html';
export type DiffRendererData =
  | { kind: 'text'; previewKind?: DiffPreviewKind }
  | { kind: 'image' }
  | { kind: 'binary' };

export interface DiffPayload {
  readonly path: GitFilePath;
  diffGroup: 'disk' | 'staged' | 'git' | 'pr';
  originalRef: GitObjectRef;
  modifiedRef?: GitObjectRef;
  prNumber?: number;
  prBaseOid?: string;
  prHeadOid?: string;
  commitOriginalSha?: string | null;
  commitModifiedSha?: string;
  status?: GitChangeStatus;
}

/**
 * Domain resource for a single open diff tab.
 *
 * Replaces DiffTabStore. The identity fields (tabId, kind, isPreview) live on
 * TabEntry; this class holds only the live/mutable diff state.
 *
 * Holds tabId so that DiffTabLifecycleStore can call pane.closeTab(resource.tabId).
 */
export class DiffTabResource implements TabResource {
  /** Provided so lifecycle stores can close/transition by tabId. */
  readonly tabId: string;

  readonly path: GitFilePath;
  viewMode: DiffViewMode = 'diff';
  renderer: DiffRendererData;
  diffGroup: 'disk' | 'staged' | 'git' | 'pr';
  originalRef: GitObjectRef;
  modifiedRef: GitObjectRef | undefined;
  prNumber: number | undefined;
  prBaseOid: string | undefined;
  prHeadOid: string | undefined;
  commitOriginalSha: string | null | undefined;
  commitModifiedSha: string | undefined;
  status: GitChangeStatus | undefined;

  private readonly _manager: DiffTabManager | null;
  private readonly _handle: TabHandle | null;

  constructor(tabId: string, payload: DiffPayload, manager?: DiffTabManager, handle?: TabHandle) {
    this.tabId = tabId;
    this.path = payload.path;
    this._manager = manager ?? null;
    this._handle = handle ?? null;
    this.renderer = resolveDiffRenderer(payload.path);
    this.diffGroup = payload.diffGroup;
    this.originalRef = payload.originalRef;
    this.modifiedRef = payload.modifiedRef;
    this.prNumber = payload.prNumber;
    this.prBaseOid = payload.prBaseOid;
    this.prHeadOid = payload.prHeadOid;
    this.commitOriginalSha = payload.commitOriginalSha;
    this.commitModifiedSha = payload.commitModifiedSha;
    this.status = payload.status;

    makeObservable(this, {
      viewMode: observable,
      renderer: observable,
      diffGroup: observable,
      originalRef: observable,
      modifiedRef: observable,
      prNumber: observable,
      prBaseOid: observable,
      prHeadOid: observable,
      commitOriginalSha: observable,
      commitModifiedSha: observable,
      status: observable,
      setViewMode: action,
      transition: action,
      updateStatus: action,
    });

    this._manager?.acquire(this);
  }

  /** Sync the bound DiffViewStore when this tab is activated (engine-called). */
  onActivate(): void {
    this._manager?.currentDiffView()?.setActiveFile(this.toActiveFile());
  }

  /** Force-close this tab without user confirmation — used by DiffTabManager staleness reconcile. */
  closeSelf(): void {
    void this._handle?.close({ force: true });
  }

  dispose(): void {
    this._manager?.release(this);
  }

  setViewMode(viewMode: DiffViewMode): void {
    this.viewMode = viewMode;
  }

  /**
   * Transitions this diff tab between 'disk' and 'staged' groups in-place.
   * Called by DiffTabLifecycleStore when a file moves between the staged/unstaged lists.
   */
  transition(
    newGroup: 'disk' | 'staged',
    newOriginalRef: GitObjectRef,
    status?: GitChangeStatus
  ): void {
    this.diffGroup = newGroup;
    this.originalRef = newOriginalRef;
    this.modifiedRef = undefined;
    this.prNumber = undefined;
    this.prBaseOid = undefined;
    this.prHeadOid = undefined;
    this.commitOriginalSha = undefined;
    this.commitModifiedSha = undefined;
    this.status = status;
    this.renderer = resolveDiffRenderer(this.path);
  }

  /** Update the status field without changing diff group/refs. */
  updateStatus(status: GitChangeStatus | undefined): void {
    this.status = status;
  }

  toActiveFile(): ActiveFile {
    return {
      path: this.path,
      type: this.diffGroup === 'disk' ? 'disk' : 'git',
      group: this.diffGroup,
      originalRef: this.originalRef,
      modifiedRef: this.modifiedRef,
      prNumber: this.prNumber,
      prBaseOid: this.prBaseOid,
      prHeadOid: this.prHeadOid,
      commitOriginalSha: this.commitOriginalSha,
      commitModifiedSha: this.commitModifiedSha,
    };
  }
}

function resolveDiffRenderer(path: string): DiffRendererData {
  const kind = getFileKind(path);
  if (kind === 'markdown' || kind === 'html') return { kind: 'text', previewKind: kind };
  if (kind === 'image' || kind === 'svg') return { kind: 'image' };
  if (kind === 'binary') return { kind: 'binary' };
  return { kind: 'text' };
}
