import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

/**
 * The retirement migration train (0032 value rewrites + backfills, 0033
 * index/column drops, 0034 deleted_at → untracked_at rename) is a one-way
 * door. The pre-0032 fixture carries legacy vocabulary (project-root/path
 * kinds), a BYOI row with a bound task, a project without a repository link,
 * and host identity stored on the projects table.
 */

const PROJECT_A_ID = '11111111-1111-1111-1111-111111111111';
const PROJECT_B_ID = '22222222-2222-2222-2222-222222222222';
const PROJECT_REMOTE_ID = '33333333-3333-3333-3333-333333333333';
const SSH_CONNECTION_ID = '99999999-9999-9999-9999-999999999999';

const PROJECT_A_REPOSITORY_WORKSPACE_ID = 'eeee0001-0000-0000-0000-000000000000';
const PROJECT_REMOTE_REPOSITORY_WORKSPACE_ID = 'eeee0002-0000-0000-0000-000000000000';
const DUPLICATE_DROP_WORKSPACE_ID = 'eeee0005-0000-0000-0000-000000000000';
const BYOI_WORKSPACE_ID = 'ffff0001-0000-0000-0000-000000000000';
const PLAIN_DIR_WORKSPACE_ID = 'ffff0002-0000-0000-0000-000000000000';
const BYOI_TASK_ID = 'aaaa0004-0000-0000-0000-000000000000';

describe('0032-0034 retirement migration train', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('pre-0032');
  });

  afterEach(() => {
    fixture?.close();
  });

  it('rewrites the kind vocabulary to repository|worktree|directory', () => {
    const kinds = fixture.sqlite
      .prepare(`SELECT DISTINCT kind FROM workspaces ORDER BY kind`)
      .all() as { kind: string | null }[];
    expect(kinds.map((row) => row.kind)).toEqual(['directory', 'repository', 'worktree']);

    const repoA = fixture.sqlite
      .prepare(`SELECT kind FROM workspaces WHERE id = ?`)
      .get(PROJECT_A_REPOSITORY_WORKSPACE_ID) as { kind: string };
    expect(repoA.kind).toBe('repository');

    const plainDir = fixture.sqlite
      .prepare(`SELECT kind FROM workspaces WHERE id = ?`)
      .get(PLAIN_DIR_WORKSPACE_ID) as { kind: string };
    expect(plainDir.kind).toBe('directory');
  });

  it('untracks BYOI rows and rewrites their type, keeping bound tasks intact', () => {
    const byoi = fixture.sqlite
      .prepare(`SELECT kind, type, untracked_at FROM workspaces WHERE id = ?`)
      .get(BYOI_WORKSPACE_ID) as { kind: string; type: string; untracked_at: string | null };
    expect(byoi.untracked_at).not.toBeNull();
    expect(byoi.kind).toBe('directory');
    expect(byoi.type).toBe('project-ssh');

    // The bound task keeps its workspace_id; missing-workspace surfaces in UI.
    const task = fixture.sqlite
      .prepare(`SELECT workspace_id FROM tasks WHERE id = ?`)
      .get(BYOI_TASK_ID) as { workspace_id: string };
    expect(task.workspace_id).toBe(BYOI_WORKSPACE_ID);
  });

  it('backfills a repository workspace row for every live project', () => {
    const rows = fixture.sqlite
      .prepare(
        `SELECT projects.id AS project_id, workspaces.id AS workspace_id,
                workspaces.kind, workspaces.location, workspaces.ssh_connection_id,
                workspaces.path
         FROM projects
         INNER JOIN workspaces ON workspaces.id = projects.repository_workspace_id
         WHERE projects.deleted_at IS NULL`
      )
      .all() as Array<{
      project_id: string;
      workspace_id: string;
      kind: string;
      location: string;
      ssh_connection_id: string | null;
      path: string;
    }>;

    expect(rows).toHaveLength(3);
    const byProject = new Map(rows.map((row) => [row.project_id, row]));

    expect(byProject.get(PROJECT_A_ID)).toMatchObject({
      workspace_id: PROJECT_A_REPOSITORY_WORKSPACE_ID,
      kind: 'repository',
      location: 'local',
      path: '/home/dev/projects/emdash',
    });
    // Project B had no repository link — the train creates and links one.
    expect(byProject.get(PROJECT_B_ID)).toMatchObject({
      kind: 'repository',
      location: 'local',
      ssh_connection_id: null,
      path: '/home/dev/projects/my-api',
    });
    expect(byProject.get(PROJECT_REMOTE_ID)).toMatchObject({
      workspace_id: PROJECT_REMOTE_REPOSITORY_WORKSPACE_ID,
      kind: 'repository',
      location: 'remote',
      ssh_connection_id: SSH_CONNECTION_ID,
      path: '/srv/repos/remote-api',
    });
  });

  it('drops the retired columns from projects, tasks, and workspaces', () => {
    const projectColumns = (
      fixture.sqlite.prepare(`PRAGMA table_info('projects')`).all() as { name: string }[]
    ).map((column) => column.name);
    expect(projectColumns).not.toContain('path');
    expect(projectColumns).not.toContain('workspace_provider');
    expect(projectColumns).not.toContain('ssh_connection_id');

    const taskColumns = (
      fixture.sqlite.prepare(`PRAGMA table_info('tasks')`).all() as { name: string }[]
    ).map((column) => column.name);
    expect(taskColumns).not.toContain('workspace_intent');
    expect(taskColumns).not.toContain('workspace_provider');
    expect(taskColumns).not.toContain('workspace_provider_data');

    const workspaceColumns = (
      fixture.sqlite.prepare(`PRAGMA table_info('workspaces')`).all() as { name: string }[]
    ).map((column) => column.name);
    expect(workspaceColumns).not.toContain('key');
    expect(workspaceColumns).not.toContain('branch_name');
    expect(workspaceColumns).not.toContain('data');
    expect(workspaceColumns).not.toContain('deleted_at');
    expect(workspaceColumns).toContain('untracked_at');
  });

  it('renames deleted_at to untracked_at preserving values', () => {
    const untracked = fixture.sqlite
      .prepare(`SELECT untracked_at FROM workspaces WHERE id = ?`)
      .get(DUPLICATE_DROP_WORKSPACE_ID) as { untracked_at: string | null };
    expect(untracked.untracked_at).toBe('2026-04-02T10:00:00.000Z');
  });

  it('drops the legacy indexes and keeps the registry identity indexes', () => {
    const projectIndexes = (
      fixture.sqlite.prepare(`PRAGMA index_list('projects')`).all() as { name: string }[]
    ).map((index) => index.name);
    expect(projectIndexes).not.toContain('idx_projects_local_path');
    expect(projectIndexes).not.toContain('idx_projects_remote_path');
    expect(projectIndexes).not.toContain('idx_projects_ssh_connection_id');
    expect(projectIndexes).toContain('idx_projects_repository_workspace_id');

    const workspaceIndexes = (
      fixture.sqlite.prepare(`PRAGMA index_list('workspaces')`).all() as { name: string }[]
    ).map((index) => index.name);
    expect(workspaceIndexes).not.toContain('idx_workspaces_key');
    expect(workspaceIndexes).toContain('idx_workspaces_local_path');
    expect(workspaceIndexes).toContain('idx_workspaces_remote_path');

    const localPathIndex = fixture.sqlite
      .prepare(
        `SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_workspaces_local_path'`
      )
      .get() as { sql: string };
    expect(localPathIndex.sql).toContain('untracked_at');
  });

  it('recreates the projects table without cascading into child rows', () => {
    // The projects table is recreated in 0033 (DROP + RENAME). With foreign
    // keys enforced that DROP would cascade-delete tasks, settings, and
    // remotes — the runner disables enforcement around the transaction.
    const taskCount = fixture.sqlite.prepare(`SELECT count(*) AS n FROM tasks`).get() as {
      n: number;
    };
    expect(taskCount.n).toBe(6);

    const conversationCount = fixture.sqlite
      .prepare(`SELECT count(*) AS n FROM conversations`)
      .get() as { n: number };
    expect(conversationCount.n).toBeGreaterThan(0);

    const settingsCount = fixture.sqlite
      .prepare(`SELECT count(*) AS n FROM project_settings`)
      .get() as { n: number };
    expect(settingsCount.n).toBe(3);

    const violations = fixture.sqlite.prepare(`PRAGMA foreign_key_check`).all();
    expect(violations).toEqual([]);
  });
});
