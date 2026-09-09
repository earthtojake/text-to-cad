import { WorkspaceStore } from '@core/features/workspaces/api/browser/stores/workspace';
import type { WorkspaceScopedStoreContext } from '@core/features/workspaces/contributions/browser/workspace-stores';

type WorkspaceRegistryEntry = {
  store: WorkspaceStore;
  refCount: number;
  activated: boolean;
};

export class WorkspaceRegistryStore {
  private readonly entries = new Map<string, WorkspaceRegistryEntry>();
  acquire(context: WorkspaceScopedStoreContext): WorkspaceStore {
    const existing = this.entries.get(context.workspaceId);
    if (existing) {
      if (
        existing.store.path === context.path &&
        existing.store.sshConnectionId === context.sshConnectionId
      ) {
        existing.refCount += 1;
        return existing.store;
      }
      existing.store.dispose();
    }

    const store = new WorkspaceStore(context);
    this.entries.set(context.workspaceId, { store, refCount: 1, activated: false });
    return store;
  }

  get(workspaceId: string): WorkspaceStore | undefined {
    return this.entries.get(workspaceId)?.store;
  }

  activate(workspaceId: string): void {
    const entry = this.entries.get(workspaceId);
    if (!entry || entry.activated) {
      return;
    }
    entry.activated = true;
    entry.store.activate();
  }

  release(workspaceId: string, expectedStore?: WorkspaceStore): void {
    const entry = this.entries.get(workspaceId);
    if (!entry || (expectedStore && entry.store !== expectedStore)) {
      return;
    }

    entry.refCount -= 1;

    if (entry.refCount <= 0) {
      entry.store.dispose();
      this.entries.delete(workspaceId);
    }
  }
}

export const workspaceRegistry = new WorkspaceRegistryStore();
