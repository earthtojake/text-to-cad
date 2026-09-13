import { describe, expect, it } from 'vitest';
import {
  projectWorkspaceOpenInTaskDisabledReason,
  type ProjectWorkspaceRow,
} from './project-workspaces';

describe('projectWorkspaceOpenInTaskDisabledReason', () => {
  it('allows a present registered workspace', () => {
    expect(projectWorkspaceOpenInTaskDisabledReason(workspaceRow())).toBeUndefined();
  });

  it('refuses unregistered, missing, and pending-removal rows', () => {
    expect(projectWorkspaceOpenInTaskDisabledReason(workspaceRow({ workspaceId: null }))).toBe(
      'This workspace is not registered.'
    );
    expect(
      projectWorkspaceOpenInTaskDisabledReason(
        workspaceRow({ observedStatus: 'missing', pathState: 'missing' })
      )
    ).toBe('This workspace path is no longer available.');
    expect(projectWorkspaceOpenInTaskDisabledReason(workspaceRow({ pendingRemoval: true }))).toBe(
      'This workspace is being removed.'
    );
  });
});

function workspaceRow(overrides: Partial<ProjectWorkspaceRow> = {}): ProjectWorkspaceRow {
  return {
    kind: 'workspace',
    projectId: 'project-1',
    workspaceId: 'workspace-1',
    path: '/repo/workspace-1',
    tasks: [],
    usage: null,
    gitStats: null,
    pathState: 'measured',
    canCleanArtifacts: true,
    canDelete: true,
    hasActiveSessions: false,
    pendingRemoval: false,
    errors: [],
    ...overrides,
  };
}
