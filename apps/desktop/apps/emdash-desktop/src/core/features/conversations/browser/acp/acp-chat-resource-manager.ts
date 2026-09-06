import { getProjectHostAccess } from '@core/features/projects/api/browser/stores/project-selectors';
import { AcpChatStore } from './acp-chat-store';

const GRACE_MS = 5_000;

type Entry = {
  store: AcpChatStore;
  refCount: number;
  graceTimer: ReturnType<typeof setTimeout> | null;
};

/**
 * Per-task ref-counted manager for AcpChatStore instances.
 *
 * Replaces acpChatRegistry for tab-lifecycle purposes.
 * Each distinct conversationId is ref-counted; the store is disposed
 * after GRACE_MS once the last retain is released.
 */
export class AcpChatResourceManager {
  private readonly _entries = new Map<string, Entry>();

  constructor(
    private readonly projectId: string,
    private readonly taskId: string
  ) {}

  acquire(conversationId: string): AcpChatStore {
    let entry = this._entries.get(conversationId);
    if (entry) {
      entry.refCount++;
      if (entry.graceTimer !== null) {
        clearTimeout(entry.graceTimer);
        entry.graceTimer = null;
      }
      return entry.store;
    }
    const store = new AcpChatStore(
      conversationId,
      this.projectId,
      this.taskId,
      getProjectHostAccess(this.projectId)
    );
    entry = { store, refCount: 1, graceTimer: null };
    this._entries.set(conversationId, entry);
    return store;
  }

  get(conversationId: string): AcpChatStore | undefined {
    return this._entries.get(conversationId)?.store;
  }

  release(conversationId: string): void {
    const entry = this._entries.get(conversationId);
    if (!entry) return;
    entry.refCount = Math.max(0, entry.refCount - 1);
    if (entry.refCount > 0) return;

    // Schedule disposal after grace period.
    entry.graceTimer = setTimeout(() => {
      const e = this._entries.get(conversationId);
      if (!e || e.refCount > 0) return;
      e.store.dispose();
      this._entries.delete(conversationId);
    }, GRACE_MS);
  }

  dispose(): void {
    for (const [, entry] of this._entries) {
      if (entry.graceTimer !== null) clearTimeout(entry.graceTimer);
      entry.store.dispose();
    }
    this._entries.clear();
  }
}

const _registry = new Map<string, AcpChatResourceManager>();

export function getAcpChatResourceManager(
  taskId: string,
  projectId: string
): AcpChatResourceManager {
  const existing = _registry.get(taskId);
  if (existing) return existing;
  const manager = new AcpChatResourceManager(projectId, taskId);
  _registry.set(taskId, manager);
  return manager;
}

export function releaseAcpChatResourceManager(taskId: string): void {
  const manager = _registry.get(taskId);
  if (!manager) return;
  manager.dispose();
  _registry.delete(taskId);
}
