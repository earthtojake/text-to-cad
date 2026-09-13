import type { GitChange } from '@emdash/core/runtimes/git/api';
import { useQuery } from '@tanstack/react-query';
import {
  checkoutSelector,
  getSourceControlClient,
} from '@core/features/source-control/api/browser/client';

export const commitFilesQueryKey = (projectId: string, workspaceId: string, commitHash: string) =>
  [projectId, workspaceId, 'commit-files', commitHash] as const;

export function useCommitFiles(
  projectId: string,
  workspaceId: string,
  commitHash: string,
  enabled: boolean
) {
  return useQuery({
    queryKey: commitFilesQueryKey(projectId, workspaceId, commitHash),
    queryFn: async (): Promise<GitChange[]> => {
      const client = await getSourceControlClient();
      const result = await client.checkout.getCommitFiles({
        ...checkoutSelector(workspaceId),
        hash: commitHash,
      });
      if (!result.success) throw new Error('Failed to load commit files');
      return result.data.files;
    },
    enabled,
    staleTime: 5 * 60_000,
  });
}
