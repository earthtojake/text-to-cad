import {
  shortName,
  type CheckoutHeadState,
  type GitBranchRef,
} from '@emdash/core/runtimes/git/api';
import { useQuery } from '@tanstack/react-query';
import {
  asAvailableProject,
  getProjectStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import {
  inspectProjectPath,
  readCheckoutHead,
} from '@core/features/source-control/api/browser/client';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';

export type ProjectGitContext = {
  defaultBranch: GitBranchRef | undefined;
  currentBranch: string | null;
  isUnborn: boolean;
  hasRepository: boolean;
  repositoryWorkspaceId: string | null;
};

function branchNameFromHead(head: CheckoutHeadState | undefined): string | null {
  if (!head || head.kind === 'detached') return null;
  return shortName(head.ref);
}

export function useProjectGitContext(projectId: string | undefined): ProjectGitContext {
  const context = projectId ? asAvailableProject(getProjectStore(projectId)) : undefined;
  const project = context?.project;
  const repo = projectId ? getGitRepositoryStore(projectId) : undefined;

  const pathInspectionQuery = useQuery({
    queryKey: ['projectPathStatus', 'taskConfig', projectId, project?.path],
    enabled: !!project,
    queryFn: async () => {
      if (!project) throw new Error('Project context is unavailable');
      return project.type === 'ssh'
        ? inspectProjectPath({
            type: 'ssh',
            connectionId: project.connectionId,
            path: project.path,
          })
        : inspectProjectPath({
            type: 'local',
            path: project.path,
          });
    },
    refetchOnWindowFocus: true,
  });

  const headQuery = useQuery({
    queryKey: ['gitRepository', 'projectRootHead', projectId],
    enabled: !!project?.repositoryWorkspaceId,
    queryFn: async () => {
      if (!project?.repositoryWorkspaceId) throw new Error('Repository workspace required');
      return readCheckoutHead(project.repositoryWorkspaceId);
    },
    refetchOnWindowFocus: true,
  });

  const head = headQuery.data;
  return {
    defaultBranch: repo?.defaultBranchRef,
    currentBranch: branchNameFromHead(head),
    isUnborn: head?.kind === 'unborn',
    hasRepository: pathInspectionQuery.data?.error
      ? true
      : (pathInspectionQuery.data?.isGitRepo ?? true),
    repositoryWorkspaceId: project?.repositoryWorkspaceId ?? null,
  };
}
