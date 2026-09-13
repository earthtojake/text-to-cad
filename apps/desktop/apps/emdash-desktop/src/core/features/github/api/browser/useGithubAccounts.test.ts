import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';
import { invalidateGitHubAccountState } from './useGithubAccounts';

function isInvalidated(queryClient: QueryClient, queryKey: readonly unknown[]): boolean {
  const query = queryClient.getQueryCache().find({ queryKey, exact: true });
  if (!query) throw new Error(`query ${JSON.stringify(queryKey)} not found`);
  return query.state.isInvalidated;
}

describe('invalidateGitHubAccountState', () => {
  it('invalidates every query whose payload depends on the connected accounts', () => {
    const queryClient = new QueryClient();
    const accountDependent = [
      ['github:accounts'],
      ['github:account-state'],
      ['issues:connection-status'],
      // Issue queries carry the account-unavailable reporting state (§7), so
      // the issue picker's connect empty state must re-resolve after connect.
      ['issues:initial', 'github', 'project-1', '', 'https://github.com/o/r', 50],
      ['issues:search', 'github', 'project-1', '', 'https://github.com/o/r', 'bug', 20],
    ] as const;
    for (const queryKey of accountDependent) {
      queryClient.setQueryData(queryKey, {});
    }
    queryClient.setQueryData(['unrelated'], {});

    invalidateGitHubAccountState(queryClient);

    for (const queryKey of accountDependent) {
      expect(isInvalidated(queryClient, queryKey), JSON.stringify(queryKey)).toBe(true);
    }
    expect(isInvalidated(queryClient, ['unrelated'])).toBe(false);
  });
});
