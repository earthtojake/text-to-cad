import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { getGithubClient } from './client';

export const GITHUB_ACCOUNTS_QUERY_KEY = ['github:accounts'] as const;
export const GITHUB_ACCOUNT_STATE_QUERY_KEY = ['github:account-state'] as const;
export const ISSUE_CONNECTION_STATUS_QUERY_KEY = ['issues:connection-status'] as const;
// Prefixes of the issue queries in `use-issues.ts`, whose payloads carry the
// account-unavailable reporting state (spec: github-git-settings §7).
const ISSUE_LIST_QUERY_PREFIXES = [['issues:initial'], ['issues:search']] as const;

/**
 * Invalidates every query whose result depends on the connected GitHub
 * accounts, so surfaces rendering the §7 reporting matrix (identity strips,
 * issue picker, PR selector) re-resolve after an account connects or leaves.
 */
export function invalidateGitHubAccountState(queryClient: QueryClient) {
  void queryClient.invalidateQueries({ queryKey: GITHUB_ACCOUNTS_QUERY_KEY });
  void queryClient.invalidateQueries({ queryKey: GITHUB_ACCOUNT_STATE_QUERY_KEY });
  void queryClient.invalidateQueries({ queryKey: ISSUE_CONNECTION_STATUS_QUERY_KEY });
  for (const queryKey of ISSUE_LIST_QUERY_PREFIXES) {
    void queryClient.invalidateQueries({ queryKey });
  }
}

export function useGitHubAccounts() {
  return useQuery({
    queryKey: GITHUB_ACCOUNTS_QUERY_KEY,
    queryFn: async () => (await getGithubClient()).listAccounts(undefined),
    staleTime: 30_000,
    refetchOnWindowFocus: true,
  });
}

export function useImportGitHubCliAccounts() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await getGithubClient()).importCliAccounts(undefined),
    onSuccess: () => invalidateGitHubAccountState(queryClient),
  });
}

export function useGitHubDeviceFlowAuth() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => (await getGithubClient()).auth(undefined),
    onSettled: () => invalidateGitHubAccountState(queryClient),
  });
}

export function useSetDefaultGitHubAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (accountId: string) =>
      (await getGithubClient()).setDefaultAccount({ accountId }),
    onSuccess: () => invalidateGitHubAccountState(queryClient),
  });
}

export function useRemoveGitHubAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (accountId: string) => (await getGithubClient()).removeAccount({ accountId }),
    onSuccess: () => invalidateGitHubAccountState(queryClient),
  });
}
