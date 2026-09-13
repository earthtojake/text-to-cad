import { useMemo } from 'react';
import {
  getProjectStore,
  projectData,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { useWorkspaceGroups } from '@core/features/workspaces/api/browser/use-workspace-groups';
import { projectWorkspaceOption } from './project-workspace-options';

/**
 * Projects the same live workspace-registry model used by Project Settings into
 * task-creation options. This deliberately includes unlinked/adopted workspaces.
 */
export function useProjectWorkspaceOptions(projectId: string | undefined) {
  const project = projectId ? projectData(getProjectStore(projectId)) : null;
  const scope =
    project?.type === 'ssh'
      ? ({ kind: 'machine', machineId: project.connectionId } as const)
      : ({ kind: 'local' } as const);
  const query = useWorkspaceGroups(scope, !!projectId && !!project);
  const group = query.data?.find((candidate) => candidate.project.id === projectId);
  const data = useMemo(
    () => group?.workspaces.map(projectWorkspaceOption) ?? [],
    [group?.workspaces]
  );

  return { ...query, data };
}
