import type { GitBranchRef } from '@emdash/core/runtimes/git/api';
import { observer } from 'mobx-react-lite';
import React from 'react';
import {
  asAvailableProject,
  getProjectStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import {
  BranchSelector,
  type BranchLabelRemoteMode,
} from '@core/features/source-control/browser/components/branch-selector';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';

export interface ProjectBranchSelectorProps {
  projectId: string;
  value?: GitBranchRef;
  onValueChange: (value: GitBranchRef) => void;
  remoteOnly?: boolean;
  remoteName?: string;
  branchLabelRemote?: BranchLabelRemoteMode;
  trigger?: React.ReactNode;
  showRemoteSelectorFooter?: boolean;
}

export const ProjectBranchSelector = observer(function ProjectBranchSelector({
  projectId,
  value,
  onValueChange,
  remoteOnly,
  remoteName,
  branchLabelRemote,
  trigger,
  showRemoteSelectorFooter = false,
}: ProjectBranchSelectorProps) {
  const repo = getGitRepositoryStore(projectId);
  const context = asAvailableProject(getProjectStore(projectId));
  const refreshDisabledReason = context
    ? projectAvailabilityUi.getLiveActionDisabledReason(projectId)
    : 'Unavailable until access to this Project is restored.';
  // The effective base remote from the resolver; undefined at zero remotes,
  // which simply hides the remote-selector footer (no remote branches exist).
  const selectedRemoteName =
    remoteName ??
    (value?.type === 'remote' ? value.remote.name : undefined) ??
    repo?.baseRemote?.name ??
    undefined;

  const branches: GitBranchRef[] = repo?.branchRefs ?? [];
  const canSelectRemote = showRemoteSelectorFooter && remoteName === undefined;

  return (
    <BranchSelector
      branches={branches}
      value={value}
      onValueChange={onValueChange}
      remoteOnly={remoteOnly}
      branchLabelRemote={branchLabelRemote}
      trigger={trigger}
      onRefresh={() => repo?.refresh()}
      refreshDisabledReason={refreshDisabledReason}
      observationKind={repo?.refsObservation.kind ?? 'unavailable'}
      isRefreshing={repo?.loading ?? false}
      remotes={canSelectRemote ? repo?.remotes : undefined}
      selectedRemoteName={
        showRemoteSelectorFooter || remoteName !== undefined ? selectedRemoteName : undefined
      }
    />
  );
});
