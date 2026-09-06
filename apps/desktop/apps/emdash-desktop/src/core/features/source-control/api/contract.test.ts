import { gitContract } from '@emdash/core/runtimes/git/api';
import { describe, expect, it } from 'vitest';
import { sourceControlContract } from './contract';

describe('sourceControlContract', () => {
  it('keeps the repository and checkout surfaces aligned with the Git runtime', () => {
    expect(Object.keys(sourceControlContract.repository)).toEqual(
      Object.keys(gitContract.repository)
    );
    // `content` is intentionally not relayed: git-ref file content is served
    // through the files domain (OpenFileStore git facets), not source-control.
    expect(Object.keys(sourceControlContract.checkout)).toEqual(
      Object.keys(gitContract.checkout).filter((key) => key !== 'content')
    );
    expect(Object.keys(sourceControlContract.repository.model.states)).toEqual(
      Object.keys(gitContract.repository.model.states)
    );
    expect(Object.keys(sourceControlContract.repository.model.mutations)).toEqual(
      Object.keys(gitContract.repository.model.mutations)
    );
    expect(Object.keys(sourceControlContract.checkout.model.states)).toEqual(
      Object.keys(gitContract.checkout.model.states)
    );
    expect(Object.keys(sourceControlContract.checkout.model.mutations)).toEqual(
      Object.keys(gitContract.checkout.model.mutations)
    );
  });

  it('uses application identities instead of host paths', () => {
    expect(
      sourceControlContract.repository.model.keySchema.parse({ projectId: 'project-1' })
    ).toEqual({ projectId: 'project-1' });
    expect(
      sourceControlContract.checkout.model.keySchema.parse({ workspaceId: 'workspace-1' })
    ).toEqual({ workspaceId: 'workspace-1' });
    expect(() =>
      sourceControlContract.repository.model.keySchema.parse({ repository: '/repo' })
    ).toThrow();
    expect(() =>
      sourceControlContract.checkout.model.keySchema.parse({ checkout: '/repo/worktree' })
    ).toThrow();
  });
});
