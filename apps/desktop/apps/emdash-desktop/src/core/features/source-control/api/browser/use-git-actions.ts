import { useMutation } from '@tanstack/react-query';
import {
  runGitFetch,
  runGitPublishCurrentBranch,
  runGitPull,
  runGitPush,
} from '@core/features/source-control/api/browser/git-action-handlers';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import { getTaskGitCheckoutStore } from '@core/features/source-control/api/browser/stores/task-source-control-selectors';

export function useGitActions(projectId: string, taskId: string) {
  const git = getTaskGitCheckoutStore(projectId, taskId)!;
  const repository = getGitRepositoryStore(projectId)!;
  const isPublished = git.isPublished;

  const gitFetchMutation = useMutation({
    mutationFn: () => runGitFetch(repository),
  });

  const gitPullMutation = useMutation({
    mutationFn: () => runGitPull(git),
  });

  const gitPushMutation = useMutation({
    mutationFn: () => runGitPush(git),
  });

  const gitPublishMutation = useMutation({
    mutationFn: () => runGitPublishCurrentBranch(git),
  });

  return {
    isPublished,
    aheadCount: git.aheadCount,
    behindCount: git.behindCount,
    publish: () => gitPublishMutation.mutate(),
    isPublishing: gitPublishMutation.isPending,
    fetch: () => gitFetchMutation.mutate(),
    isFetching: gitFetchMutation.isPending,
    pull: () => gitPullMutation.mutate(),
    isPulling: gitPullMutation.isPending,
    push: () => gitPushMutation.mutate(),
    isPushing: gitPushMutation.isPending,
  };
}
