import type { WorkspaceLifecycleStepInfo } from '@core/primitives/tasks/api';

/**
 * Render-time titles for the workspace lifecycle step vocabulary — the single copy
 * source for the create-task preview ("what will happen") and the Activity badge
 * ("what is happening"), so the two surfaces cannot drift apart.
 */
export const LIFECYCLE_STEP_TITLES: Record<WorkspaceLifecycleStepInfo['id'], string> = {
  'adopt-worktree': 'Adopt worktree',
  'fetch-branch': 'Fetch branch',
  'fetch-remote-base': 'Fetch remote base',
  'create-worktree': 'Create worktree',
  'configure-branch': 'Configure branch',
  'copy-artifacts': 'Copy artifacts',
  'push-branch': 'Push branch',
  'fetch-refs': 'Fetch refs',
  prepare: 'Prepare',
  setup: 'Setup',
  run: 'Run',
  teardown: 'Teardown',
};
