import type { GitBranchRef } from '@emdash/core/runtimes/git/api';
import { useCallback, useState } from 'react';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';

export type BranchSelectionState = ReturnType<typeof useBranchSelection>;

export type BranchSelectionInitial = {
  createBranchAndWorktree?: boolean;
  pushBranch?: boolean;
  branchOverride?: GitBranchRef;
};

export function useBranchSelection(
  selectedProjectId: string | undefined,
  defaultBranch: GitBranchRef | undefined,
  currentBranchName: string | null,
  isUnborn: boolean,
  initial?: BranchSelectionInitial,
  createBranchAndWorktreeByDefault = true
) {
  const { value: project } = useAppSettingsKey('project');
  const pushOnCreateByDefault = project?.pushOnCreate ?? true;

  const [createBranchAndWorktreeOverride, setCreateBranchAndWorktreeOverride] = useState<
    boolean | undefined
  >(initial?.createBranchAndWorktree);
  const [pushBranchOverride, setPushBranchOverride] = useState<boolean | undefined>(
    initial?.pushBranch
  );
  const pushBranch = pushBranchOverride ?? pushOnCreateByDefault;
  const createBranchAndWorktreePreference =
    createBranchAndWorktreeOverride ?? createBranchAndWorktreeByDefault;
  const createBranchAndWorktree = isUnborn ? false : createBranchAndWorktreePreference;

  // Store the user's branch override alongside the project it belongs to.
  // When the project changes the override is for a different project and is
  // ignored, so defaultBranch takes effect automatically — no effect needed.
  const [branchOverride, setBranchOverride] = useState<
    { projectId: string; branch: GitBranchRef } | undefined
  >(
    initial?.branchOverride && selectedProjectId
      ? { projectId: selectedProjectId, branch: initial.branchOverride }
      : undefined
  );

  const fallbackBranch =
    !createBranchAndWorktree &&
    currentBranchName &&
    !(initial?.createBranchAndWorktree === false && initial.branchOverride === undefined)
      ? ({ type: 'local', branch: currentBranchName } satisfies GitBranchRef)
      : defaultBranch;

  const selectedBranch: GitBranchRef | undefined =
    branchOverride !== undefined && branchOverride.projectId === selectedProjectId
      ? branchOverride.branch
      : fallbackBranch;

  const setSelectedBranch = useCallback(
    (branch: GitBranchRef | undefined) => {
      if (!selectedProjectId || !branch) {
        setBranchOverride(undefined);
        return;
      }
      setBranchOverride({ projectId: selectedProjectId, branch });
    },
    [selectedProjectId]
  );
  const setPushBranch = useCallback((value: boolean) => {
    setPushBranchOverride(value);
  }, []);
  const setCreateBranchAndWorktree = useCallback(
    (value: boolean) => {
      if (isUnborn) return;
      setCreateBranchAndWorktreeOverride(value);
    },
    [isUnborn]
  );

  return {
    selectedBranch,
    setSelectedBranch,
    createBranchAndWorktree,
    setCreateBranchAndWorktree,
    pushBranch,
    setPushBranch,
  };
}
