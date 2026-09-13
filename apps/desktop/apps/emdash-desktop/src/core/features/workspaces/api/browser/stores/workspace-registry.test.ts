import { describe, expect, it, vi } from 'vitest';
import { WorkspaceRegistryStore } from './workspace-registry';

vi.mock('@core/manifests/browser/workspace-scoped-stores', () => ({
  workspaceStoreContributions: [],
}));

function context(sshConnectionId: string) {
  return {
    projectId: 'project-1',
    workspaceId: 'workspace-1',
    path: '/tmp/workspace-1',
    gitRepository: {} as never,
    sshConnectionId,
  };
}

describe('WorkspaceRegistryStore', () => {
  it('replaces a cached workspace when its Host binding changes', () => {
    const registry = new WorkspaceRegistryStore();
    const first = registry.acquire(context('ssh-1'));
    const dispose = vi.spyOn(first, 'dispose');

    const rebound = registry.acquire(context('ssh-2'));

    expect(rebound).not.toBe(first);
    expect(rebound.sshConnectionId).toBe('ssh-2');
    expect(dispose).toHaveBeenCalledOnce();

    registry.release('workspace-1', first);
    expect(registry.get('workspace-1')).toBe(rebound);

    registry.release('workspace-1', rebound);
    expect(registry.get('workspace-1')).toBeUndefined();
  });
});
