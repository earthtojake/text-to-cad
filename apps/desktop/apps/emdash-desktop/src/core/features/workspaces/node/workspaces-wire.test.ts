import { describe, expect, it, vi } from 'vitest';
import { provisionWorkspaceErrorToWorkspaceError } from '@core/features/workspaces/node/wire-controller';

vi.mock('@core/services/app-db/node/schema', () => ({
  tasks: {},
  workspaces: {},
  conversations: {},
}));

describe('provisionWorkspaceErrorToWorkspaceError', () => {
  it('maps missing workspace errors to workspace runtime errors', () => {
    expect(provisionWorkspaceErrorToWorkspaceError({ type: 'missing-workspace' })).toEqual({
      type: 'missing-workspace',
      message: 'Workspace row is missing',
    });
  });

  it('preserves setup failure step context', () => {
    expect(
      provisionWorkspaceErrorToWorkspaceError({
        type: 'setup-failed',
        stepKind: 'git-clone',
        stepErrorType: 'clone-destination-exists',
        message: 'Destination already exists',
      })
    ).toEqual({
      type: 'setup-failed',
      stageId: 'git-clone',
      message: 'Destination already exists',
      resolutions: ['clone-destination-exists'],
    });
  });

  it('maps cancelled provisioning without setup failure context', () => {
    expect(
      provisionWorkspaceErrorToWorkspaceError({
        type: 'cancelled',
        message: 'Workspace operation was preempted by teardown',
      })
    ).toEqual({
      type: 'cancelled',
      message: 'Workspace operation was preempted by teardown',
    });
  });
});
