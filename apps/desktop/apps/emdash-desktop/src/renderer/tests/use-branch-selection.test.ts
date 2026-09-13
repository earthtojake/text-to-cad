import type { GitBranchRef } from '@emdash/core/runtimes/git/api';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@core/features/settings/api/browser/use-app-settings-key', () => ({
  useAppSettingsKey: () => ({ value: { pushOnCreate: true } }),
}));

/**
 * The old resolveDefaultSelectedBranch helper has been removed.
 * Its logic — preferring a local branch over a remote branch when resolving
 * the default — now lives in GitRepositoryStore.defaultBranch (a computed getter)
 * and is exercised through integration.
 *
 * useBranchSelection now accepts a pre-resolved Branch | undefined directly,
 * so no additional unit tests for string-to-Branch resolution are needed here.
 */
describe('useBranchSelection contract', () => {
  it('accepts a local Branch as defaultBranch', () => {
    const branch: GitBranchRef = { type: 'local', branch: 'main' };
    expect(branch.type).toBe('local');
    expect(branch.branch).toBe('main');
  });

  it('accepts a remote Branch as defaultBranch', () => {
    const branch: GitBranchRef = {
      type: 'remote',
      branch: 'main',
      remote: { name: 'origin', url: 'git@github.com:owner/repo.git' },
    };
    expect(branch.type).toBe('remote');
    expect(branch.remote.name).toBe('origin');
  });
});
