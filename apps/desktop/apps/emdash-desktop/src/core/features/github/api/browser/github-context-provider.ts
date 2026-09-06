import { useToast } from '@emdash/ui/react/primitives';
import { useQueryClient } from '@tanstack/react-query';
import React, { createContext, useCallback, useContext, useEffect } from 'react';
import type { GitHubAccountState, GitHubUser } from '@core/primitives/github/api';
import { log } from '@core/primitives/logging/browser/logger';
import { getGithubClient } from './client';
import { GITHUB_ACCOUNT_STATE_QUERY_KEY, invalidateGitHubAccountState } from './useGithubAccounts';

type GithubContextValue = {
  cancelGithubConnect: () => void;
};

const GithubContext = createContext<GithubContextValue | null>(null);

export function GithubContextProvider({ children }: { children: React.ReactNode }) {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const invalidateGitHubState = useCallback(() => {
    invalidateGitHubAccountState(queryClient);
  }, [queryClient]);

  const refreshAccountState = useCallback(
    () =>
      queryClient.fetchQuery<GitHubAccountState>({
        queryKey: GITHUB_ACCOUNT_STATE_QUERY_KEY,
        queryFn: async () => (await getGithubClient()).getAccountState(undefined),
        staleTime: 0,
      }),
    [queryClient]
  );

  const handleDeviceFlowSuccess = useCallback(
    async (flowUser: GitHubUser) => {
      log.info('[GithubContext] auth success via device flow', { user: flowUser?.login });
      void refreshAccountState();
      setTimeout(() => void refreshAccountState(), 500);
      invalidateGitHubState();
      toast('Connected to GitHub', {
        description: `Signed in as ${flowUser?.login || flowUser?.name || 'user'}`,
      });
    },
    [refreshAccountState, invalidateGitHubState, toast]
  );

  const handleDeviceFlowError = useCallback(
    (error: string) => {
      toast.error('Authentication Failed', { description: error });
    },
    [toast]
  );

  useEffect(() => {
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    void getGithubClient().then(async (client) => {
      const nextUnsubscribe = await client.events.subscribe(undefined, {
        onEvent: (event) => {
          if (event.type === 'auth-success') {
            void handleDeviceFlowSuccess(event.user);
          } else if (event.type === 'auth-error') {
            handleDeviceFlowError(event.message || event.error);
          } else if (event.type === 'accounts-changed') {
            invalidateGitHubState();
          }
        },
        onGap: invalidateGitHubState,
      });
      if (disposed) nextUnsubscribe();
      else unsubscribe = nextUnsubscribe;
    });

    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, [handleDeviceFlowSuccess, handleDeviceFlowError, invalidateGitHubState]);

  const cancelGithubConnect = useCallback(() => {
    void getGithubClient().then((client) => client.authCancel(undefined));
    toast('GitHub connection unsuccessful', { description: 'Device flow was canceled' });
  }, [toast]);

  const value: GithubContextValue = {
    cancelGithubConnect,
  };

  return React.createElement(GithubContext.Provider, { value }, children);
}

export function useGithubContext() {
  const ctx = useContext(GithubContext);
  if (!ctx) {
    throw new Error('useGithubContext must be used inside GithubContextProvider');
  }
  return ctx;
}
