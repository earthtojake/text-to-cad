import { decodeResourceUri, hostFileRef } from '@emdash/core/primitives/path/api';
import { action, computed, makeObservable, observable, runInAction } from 'mobx';
import { getEditorClient } from '@core/features/editor/api/browser/client';
import {
  openFileStore,
  type OpenFileEntry,
} from '@core/features/editor/api/browser/open-file-store/open-file-store';
import type {
  FilePayload,
  FileTabResource,
} from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import type { ProjectHostAccess } from '@core/features/projects/api/browser/stores/project-context';
import type { TaskEditorTreeState } from '@core/features/tasks/contributions/mementos';
import { hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import { log } from '@core/primitives/logging/browser/logger';
import type { MementoHandle } from '@core/primitives/mementos/browser';
import type { PaneLayoutStore } from '@core/primitives/workbench-shell/browser/tabs/pane-layout-store';
import { allOpenFileResources } from '../../../../browser/task-editor/pane-selectors';
import { FilesStore } from '../../../../browser/task-editor/stores/files-store';

/**
 * Manages file persistence (save, conflict resolution) and sidebar navigation state.
 *
 * Content state lives in the app-global OpenFileStore; file tabs hold the
 * leases. This store focuses on save commands, conflict resolution, buffer
 * restore after a crash, and the sidebar file tree.
 */
export class EditorViewStore {
  isSaving = false;
  /**
   * Workspace-absolute path of a file with a conflict pending resolution.
   * EditorProvider watches this via a MobX reaction and shows the conflict modal.
   */
  pendingConflictPath: string | null = null;

  /** Monotonic signal used by the task-level search command to focus the sidebar input. */
  fileSearchFocusRequest = 0;

  /** Monotonic signal consumed by the file tree adapter to reveal a path in the sidebar. */
  revealFileRequest: { path: string; counter: number } = { path: '', counter: 0 };

  /**
   * Per-view file-tree projection store. Created when the task session starts (`startFiles`) and
   * torn down on suspend (`disposeFiles`), so projection state lives with this view's expansion
   * state rather than being shared across all tasks on the same workspace.
   */
  files: FilesStore | null = null;

  private readonly treeSessionId: string;
  private readonly workspaceId: string;
  private readonly paneLayout: PaneLayoutStore;

  constructor(
    paneLayout: PaneLayoutStore,
    treeSessionId: string,
    workspaceId: string,
    private readonly treeHandle: MementoHandle<TaskEditorTreeState>,
    private readonly hostAccess?: ProjectHostAccess
  ) {
    this.paneLayout = paneLayout;
    this.treeSessionId = treeSessionId;
    this.workspaceId = workspaceId;

    makeObservable<EditorViewStore, 'treeHandle'>(this, {
      isSaving: observable,
      pendingConflictPath: observable,
      fileSearchFocusRequest: observable,
      revealFileRequest: observable.struct,
      files: observable.ref,
      expandedPaths: computed.struct,
      requestFileSearchFocus: action,
      requestRevealFile: action,
      treeHandle: false,
    });
  }

  get expandedPaths(): Set<string> {
    return new Set(this.treeHandle.value.expandedPaths);
  }

  requestFileSearchFocus(): void {
    this.fileSearchFocusRequest += 1;
  }

  requestRevealFile(path: string): void {
    this.revealFileRequest = {
      path,
      counter: this.revealFileRequest.counter + 1,
    };
  }

  /** Opens the per-view file-tree projection. Idempotent. */
  startFiles(workspacePath: string, sshConnectionId?: string): void {
    if (this.files) return;
    // Hardcore tasks can intentionally share one CAD workspace. Keep the live
    // tree session scoped to this task so expansion acknowledgements and loaded
    // frontiers cannot collide with another task browsing the same directory.
    const store = new FilesStore(
      this.treeSessionId,
      this.workspaceId,
      workspacePath,
      sshConnectionId,
      this.hostAccess
    );
    runInAction(() => {
      this.files = store;
    });
    void store.start();
  }

  /** Closes the projection subscription and clears the per-view tree state. */
  disposeFiles(): void {
    const store = this.files;
    runInAction(() => {
      this.files = null;
    });
    store?.dispose();
  }

  /** Union of all open file resources across all panes. */
  get openFileResources(): FileTabResource[] {
    return allOpenFileResources(this.paneLayout);
  }

  /** Union of all open file paths across all panes (deduplicated). */
  get openFilePaths(): string[] {
    return [...new Set(this.openFileResources.map((r) => r.path))];
  }

  expandPath(path: string): void {
    this.expandPaths([path]);
  }

  expandPaths(paths: readonly string[]): void {
    this.treeHandle.update((current) => ({
      ...current,
      expandedPaths: [...new Set([...current.expandedPaths, ...paths])],
    }));
  }

  collapsePath(path: string): void {
    this.collapsePaths([path]);
  }

  collapsePaths(paths: readonly string[]): void {
    const removed = new Set(paths);
    this.treeHandle.update((current) => ({
      ...current,
      expandedPaths: current.expandedPaths.filter((candidate) => !removed.has(candidate)),
    }));
  }

  /**
   * Rewrites open tabs after a rename/move: re-keys the OpenFileStore entry
   * first (preserving buffer text and dirty state under the new identity),
   * then retargets the pane entries so the replacement tab resources acquire
   * the re-keyed entry.
   */
  async retargetOpenFiles(oldPath: string, newPath: string): Promise<void> {
    const normalizedOld = normalizeTreePath(oldPath);
    const normalizedNew = normalizeTreePath(newPath);
    const retargets: Array<() => void> = [];
    const rekeyed = new Set<string>();

    for (const { pane } of this.paneLayout.groups) {
      for (const tab of pane.resolvedTabs) {
        if (tab.kind !== 'file') continue;
        const resource = tab.resource as FileTabResource;
        if (!isPathAffected(resource.path, normalizedOld)) continue;
        const rewritten = rewriteAffectedPath(resource.path, normalizedOld, normalizedNew);
        const ref = resource.ref;
        if (ref && !rekeyed.has(resource.path)) {
          rekeyed.add(resource.path);
          await openFileStore.rekey(ref, hostFileRef(ref.host, hostPathFromNative(rewritten)));
        }
        retargets.push(() => {
          pane.retargetEntry(tab.tabId, {
            state: { path: rewritten } satisfies FilePayload,
          });
        });
      }
    }

    for (const retarget of retargets) retarget();
    this.retargetExpandedPaths(normalizedOld, normalizedNew);
  }

  async saveFile(filePath: string): Promise<void> {
    if (this.hostAccess?.liveAction.kind === 'disabled') return;
    const entry = this.openEntryForPath(filePath);
    if (!entry?.dirty) return;

    if (entry.conflicted) {
      runInAction(() => {
        this.pendingConflictPath = filePath;
      });
      return;
    }

    runInAction(() => {
      this.isSaving = true;
    });
    try {
      const result = await openFileStore.save(entry);
      if (!result.success) {
        if (result.error.type === 'conflict') {
          runInAction(() => {
            this.pendingConflictPath = filePath;
          });
        }
        log.error('[EditorViewStore] Failed to save file:', filePath, result.error);
      }
    } catch (error) {
      log.error('[EditorViewStore] Error saving file:', error);
    } finally {
      runInAction(() => {
        this.isSaving = false;
      });
    }
  }

  async saveAllFiles(): Promise<void> {
    for (const resource of this.openFileResources) {
      if (resource.entry?.dirty) await this.saveFile(resource.path);
    }
  }

  /**
   * Resolves a pending conflict: either reloads buffer from disk ("Accept Incoming")
   * or writes the user's buffer to disk ("Keep Mine").
   */
  async resolveConflict(accept: boolean): Promise<void> {
    if (this.hostAccess?.liveAction.kind === 'disabled') return;
    const path = this.pendingConflictPath;
    if (!path) return;
    runInAction(() => {
      this.pendingConflictPath = null;
    });
    const entry = this.openEntryForPath(path);
    if (!entry) return;

    if (accept) {
      openFileStore.reloadFromDisk(entry);
    } else {
      runInAction(() => {
        this.isSaving = true;
      });
      try {
        await openFileStore.save(entry, { overwrite: true });
      } finally {
        runInAction(() => {
          this.isSaving = false;
        });
      }
    }
  }

  /**
   * Hydrates crash-recovery buffer rows into the OpenFileStore for this
   * workspace. Called by EditorProvider on mount, after the persisted pane
   * layout has re-opened the tabs whose leases the rows apply to. Rows for
   * files that are not open stay persisted untouched.
   */
  async restoreBuffers(): Promise<void> {
    // Scope the listing to this view's workspace root, which the files store
    // resolved at the renderer edge when the session started.
    const root = this.files?.rootUri;
    if (!root) return;
    try {
      const buffers = await (await getEditorClient()).listBuffers({ root });
      for (const { uri: bufferKey, content } of buffers) {
        const decoded = decodeResourceUri(bufferKey);
        if (!decoded.success) continue;
        openFileStore.hydrateBuffer(decoded.data, content);
      }
    } catch (e) {
      log.warn('[EditorViewStore] Failed to restore buffers:', e);
    }
  }

  dispose(): void {
    this.disposeFiles();
  }

  private openEntryForPath(filePath: string): OpenFileEntry | undefined {
    return this.openFileResources.find((resource) => resource.path === filePath)?.entry;
  }

  private retargetExpandedPaths(oldPath: string, newPath: string): void {
    this.treeHandle.update((current) => ({
      ...current,
      expandedPaths: [
        ...new Set(
          current.expandedPaths.map((candidate) =>
            isPathAffected(candidate, oldPath)
              ? rewriteAffectedPath(candidate, oldPath, newPath)
              : candidate
          )
        ),
      ],
    }));
  }
}

function normalizeTreePath(path: string): string {
  const normalized = path.replaceAll('\\', '/').replace(/\/+/g, '/');
  if (normalized.length > 1 && normalized.endsWith('/')) return normalized.slice(0, -1);
  return normalized;
}

function isPathAffected(candidate: string, oldPath: string): boolean {
  const normalized = normalizeTreePath(candidate);
  return normalized === oldPath || normalized.startsWith(`${oldPath}/`);
}

function rewriteAffectedPath(candidate: string, oldPath: string, newPath: string): string {
  const normalized = normalizeTreePath(candidate);
  if (normalized === oldPath) return newPath;
  return `${newPath}${normalized.slice(oldPath.length)}`;
}
