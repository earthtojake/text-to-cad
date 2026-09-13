import type { GitBranchRef } from '@emdash/core/runtimes/git/api';
import type { AppDb } from '@core/services/app-db/node/db';
import {
  conversations,
  projectRemotes,
  projects,
  projectSettings,
  sshConnections,
  tasks,
  workspaces,
} from '@core/services/app-db/node/schema';
import { toStoredBranch } from '@core/services/app-db/node/stored-branch';

const mainBranch: GitBranchRef = { type: 'local', branch: 'main' };

// Fixed UUIDs so fixture content is stable across regenerations.
const PROJECT_A_ID = '11111111-1111-1111-1111-111111111111';
const PROJECT_B_ID = '22222222-2222-2222-2222-222222222222';
const PROJECT_REMOTE_ID = '33333333-3333-3333-3333-333333333333';
const SSH_CONNECTION_ID = '99999999-9999-9999-9999-999999999999';

const TASK_A1_ID = 'aaaa0001-0000-0000-0000-000000000000';
const TASK_A2_ID = 'aaaa0002-0000-0000-0000-000000000000';
const TASK_A3_ID = 'aaaa0003-0000-0000-0000-000000000000';
const TASK_B1_ID = 'bbbb0001-0000-0000-0000-000000000000';
const TASK_REMOTE_ID = 'dddd0001-0000-0000-0000-000000000000';

const CONV_A1_ID = 'cccc0001-0000-0000-0000-000000000000';
const CONV_A2_ID = 'cccc0002-0000-0000-0000-000000000000';

const PROJECT_A_REPOSITORY_WORKSPACE_ID = 'eeee0001-0000-0000-0000-000000000000';
const PROJECT_REMOTE_REPOSITORY_WORKSPACE_ID = 'eeee0002-0000-0000-0000-000000000000';
const TASK_A1_WORKSPACE_ID = 'eeee0003-0000-0000-0000-000000000000';
const DUPLICATE_KEEP_WORKSPACE_ID = 'eeee0004-0000-0000-0000-000000000000';
const DUPLICATE_DROP_WORKSPACE_ID = 'eeee0005-0000-0000-0000-000000000000';
const TYPE_ONLY_REMOTE_WORKSPACE_ID = 'eeee0006-0000-0000-0000-000000000000';
const PROJECT_B_REPOSITORY_WORKSPACE_ID = 'eeee0007-0000-0000-0000-000000000000';

function worktreeConfig(branchName: string) {
  return {
    version: '2' as const,
    git: { kind: 'use-branch' as const, branchName },
    workspace: { kind: 'new-worktree' as const },
  };
}

/**
 * Realistic but fully synthetic dataset — no sensitive data.
 * Represents a developer's day-to-day emdash state: two projects,
 * four tasks across various lifecycle statuses, and a couple of conversations.
 */
export async function baseline(db: AppDb): Promise<void> {
  await db.insert(sshConnections).values({
    id: SSH_CONNECTION_ID,
    name: 'fixture-remote',
    host: 'fixture.example.com',
    username: 'dev',
  });

  await db.insert(projects).values([
    {
      id: PROJECT_A_ID,
      name: 'emdash',
      baseRef: 'main',
      repositoryWorkspaceId: PROJECT_A_REPOSITORY_WORKSPACE_ID,
    },
    {
      id: PROJECT_B_ID,
      name: 'my-api',
      baseRef: 'main',
      repositoryWorkspaceId: PROJECT_B_REPOSITORY_WORKSPACE_ID,
    },
    {
      id: PROJECT_REMOTE_ID,
      name: 'remote-api',
      baseRef: 'main',
      repositoryWorkspaceId: PROJECT_REMOTE_REPOSITORY_WORKSPACE_ID,
    },
  ]);

  await db.insert(workspaces).values([
    {
      id: PROJECT_A_REPOSITORY_WORKSPACE_ID,
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/home/dev/projects/emdash',
    },
    {
      id: PROJECT_B_REPOSITORY_WORKSPACE_ID,
      type: 'local',
      kind: 'repository',
      location: 'local',
      path: '/home/dev/projects/my-api',
    },
    {
      id: PROJECT_REMOTE_REPOSITORY_WORKSPACE_ID,
      type: 'project-ssh',
      kind: 'repository',
      location: 'remote',
      sshConnectionId: SSH_CONNECTION_ID,
      path: '/srv/repos/remote-api',
    },
    {
      id: TASK_A1_WORKSPACE_ID,
      type: 'local',
      kind: 'worktree',
      location: 'local',
      parentId: PROJECT_A_REPOSITORY_WORKSPACE_ID,
      path: '/home/dev/projects/emdash-worktrees/feat-workspace-db',
      config: worktreeConfig('feat/workspace-db'),
    },
    {
      id: DUPLICATE_KEEP_WORKSPACE_ID,
      type: 'local',
      kind: 'worktree',
      location: 'local',
      parentId: PROJECT_A_REPOSITORY_WORKSPACE_ID,
      path: '/home/dev/projects/emdash-worktrees/duplicate',
      config: worktreeConfig('feat/migration-testing'),
    },
    {
      id: DUPLICATE_DROP_WORKSPACE_ID,
      type: 'local',
      kind: 'worktree',
      location: 'local',
      parentId: PROJECT_A_REPOSITORY_WORKSPACE_ID,
      path: '/home/dev/projects/emdash-worktrees/duplicate',
      untrackedAt: '2026-04-02T10:00:00.000Z',
    },
    {
      id: TYPE_ONLY_REMOTE_WORKSPACE_ID,
      type: 'project-ssh',
      kind: 'worktree',
      location: 'remote',
      sshConnectionId: SSH_CONNECTION_ID,
      parentId: PROJECT_REMOTE_REPOSITORY_WORKSPACE_ID,
      path: '/srv/repos/remote-api-worktrees/type-only',
      config: worktreeConfig('feat/type-only'),
    },
  ]);

  await db.insert(projectRemotes).values([
    {
      projectId: PROJECT_A_ID,
      remoteName: 'origin',
      remoteUrl: 'https://github.com/example/emdash.git',
    },
    {
      projectId: PROJECT_B_ID,
      remoteName: 'origin',
      remoteUrl: 'https://github.com/example/my-api.git',
    },
    {
      projectId: PROJECT_REMOTE_ID,
      remoteName: 'origin',
      remoteUrl: 'git@fixture.example.com:example/remote-api.git',
    },
  ]);

  await db
    .insert(projectSettings)
    .values([
      { projectId: PROJECT_A_ID },
      { projectId: PROJECT_B_ID },
      { projectId: PROJECT_REMOTE_ID },
    ]);

  await db.insert(tasks).values([
    {
      id: TASK_A1_ID,
      projectId: PROJECT_A_ID,
      name: 'Add workspace database entity',
      status: 'in_progress',
      taskBranch: 'feat/workspace-db',
      sourceBranch: toStoredBranch(mainBranch),
      workspaceId: TASK_A1_WORKSPACE_ID,
    },
    {
      id: TASK_A2_ID,
      projectId: PROJECT_A_ID,
      name: 'Improve migration test tooling',
      status: 'review',
      taskBranch: 'feat/migration-testing',
      sourceBranch: toStoredBranch(mainBranch),
      workspaceId: DUPLICATE_KEEP_WORKSPACE_ID,
    },
    {
      id: TASK_A3_ID,
      projectId: PROJECT_A_ID,
      name: 'Fix SSH connection timeout',
      status: 'done',
      taskBranch: 'fix/ssh-timeout',
      sourceBranch: toStoredBranch(mainBranch),
      archivedAt: '2026-04-01T10:00:00.000Z',
      workspaceId: `local:${PROJECT_A_ID}:branch:fix/ssh-timeout`,
    },
    {
      id: TASK_B1_ID,
      projectId: PROJECT_B_ID,
      name: 'Add rate limiting middleware',
      status: 'todo',
      taskBranch: 'feat/rate-limiting',
      sourceBranch: toStoredBranch(mainBranch),
    },
    {
      id: TASK_REMOTE_ID,
      projectId: PROJECT_REMOTE_ID,
      name: 'Normalize remote workspace rows',
      status: 'todo',
      taskBranch: 'feat/type-only',
      sourceBranch: toStoredBranch(mainBranch),
      workspaceId: TYPE_ONLY_REMOTE_WORKSPACE_ID,
    },
  ]);

  await db.insert(conversations).values([
    {
      id: CONV_A1_ID,
      projectId: PROJECT_A_ID,
      taskId: TASK_A1_ID,
      title: 'Plan workspace schema',
      provider: 'anthropic',
      isInitialConversation: true,
    },
    {
      id: CONV_A2_ID,
      projectId: PROJECT_A_ID,
      taskId: TASK_A2_ID,
      title: 'Design fixture tooling',
      provider: 'anthropic',
      isInitialConversation: true,
    },
  ]);
}
