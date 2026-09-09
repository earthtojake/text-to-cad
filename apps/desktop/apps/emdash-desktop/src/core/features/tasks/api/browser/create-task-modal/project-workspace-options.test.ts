import { describe, expect, it } from 'vitest';
import type { ProjectWorkspaceRow } from '@core/primitives/workspaces/api';
import { projectWorkspaceOption } from './project-workspace-options';

describe('projectWorkspaceOption', () => {
  it('projects an unlinked adopted registry row into an available task option', () => {
    expect(projectWorkspaceOption(workspaceRow())).toEqual({
      key: 'project-1\0workspace-1',
      workspaceId: 'workspace-1',
      kind: 'worktree',
      path: '/repo/workspace-1',
      branchName: 'feature/one',
      linesAdded: 4,
      linesDeleted: 2,
      taskName: null,
      isLive: false,
      linkedTaskCount: 0,
    });
  });

  it('keeps a missing registry row visible but disabled', () => {
    expect(
      projectWorkspaceOption(workspaceRow({ pathState: 'missing', observedStatus: 'missing' }))
        .disabledReason
    ).toBe('This workspace path is no longer available.');
  });
});

function workspaceRow(overrides: Partial<ProjectWorkspaceRow> = {}): ProjectWorkspaceRow {
  return {
    kind: 'candidate',
    projectId: 'project-1',
    workspaceId: 'workspace-1',
    path: '/repo/workspace-1',
    branch: 'feature/one',
    tasks: [],
    usage: null,
    gitStats: { added: 4, removed: 2, ahead: 1, behind: 0 },
    pathState: 'measured',
    canCleanArtifacts: true,
    canDelete: true,
    hasActiveSessions: false,
    pendingRemoval: false,
    errors: [],
    ...overrides,
  };
}
