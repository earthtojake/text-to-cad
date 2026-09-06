import { computed, makeObservable } from 'mobx';
import { getMachinesStore } from '@core/features/machines/contributions/app-stores';
import { type WorkspaceScopedStoreContext } from '@core/features/workspaces/contributions/browser/workspace-stores';
import { workspaceStoreContributions } from '@core/manifests/browser/workspace-scoped-stores';
import {
  ScopedStoreHost,
  type ScopedStoreToken,
  type ScopedStoreValue,
} from '@core/primitives/scoped-stores/browser';
import type { ConnectionState } from '@core/primitives/ssh/api';

export class WorkspaceStore {
  readonly workspaceId: string;
  readonly path: string;
  readonly sshConnectionId: string | undefined;
  private readonly stores: ScopedStoreHost<WorkspaceScopedStoreContext>;

  get<Token extends ScopedStoreToken<unknown>>(token: Token): ScopedStoreValue<Token> {
    return this.stores.get(token);
  }

  constructor({
    projectId,
    workspaceId,
    path,
    gitRepository,
    sshConnectionId,
  }: WorkspaceScopedStoreContext) {
    makeObservable(this, { connectionState: computed });
    this.workspaceId = workspaceId;
    this.path = path;
    this.sshConnectionId = sshConnectionId;
    this.stores = new ScopedStoreHost(
      { projectId, workspaceId, path, gitRepository, sshConnectionId },
      workspaceStoreContributions
    );
  }

  get connectionState(): ConnectionState | null {
    if (!this.sshConnectionId) return null;
    return getMachinesStore().stateFor(this.sshConnectionId);
  }

  reconnect(): void {
    if (this.sshConnectionId) {
      void getMachinesStore()
        .connect(this.sshConnectionId)
        .catch(() => {});
    }
  }

  activate(): void {
    this.stores.activate();
  }

  initialize(): void {
    this.activate();
  }

  dispose(): void {
    this.stores.dispose();
  }
}
