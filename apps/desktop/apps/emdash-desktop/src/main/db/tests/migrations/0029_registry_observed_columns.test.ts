import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

const PROJECT_A_REPOSITORY_WORKSPACE_ID = 'eeee0001-0000-0000-0000-000000000000';
const PROJECT_REMOTE_REPOSITORY_WORKSPACE_ID = 'eeee0002-0000-0000-0000-000000000000';
const TASK_A1_WORKSPACE_ID = 'eeee0003-0000-0000-0000-000000000000';
const DUPLICATE_KEEP_WORKSPACE_ID = 'eeee0004-0000-0000-0000-000000000000';
const DUPLICATE_DROP_WORKSPACE_ID = 'eeee0005-0000-0000-0000-000000000000';
const TYPE_ONLY_REMOTE_WORKSPACE_ID = 'eeee0006-0000-0000-0000-000000000000';
const SSH_CONNECTION_ID = '99999999-9999-9999-9999-999999999999';

describe('0029 registry observed columns', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('adds registry observation columns with null defaults', async () => {
    fixture = await openFixture('pre-0029');

    const columns = fixture.sqlite.prepare(`PRAGMA table_info('workspaces')`).all() as {
      name: string;
    }[];

    const names = columns.map((column) => column.name);
    expect(names).toEqual(expect.arrayContaining(['parent_id', 'observed_status']));
    // The 0029 pull-scan observation columns were dropped again at head (0041)
    // once the push-based observed_git block replaced them.
    expect(names).not.toContain('observed_git_branch');
    expect(names).not.toContain('observed_data');
    expect(names).not.toContain('last_observed_at');

    const row = fixture.sqlite
      .prepare(`SELECT observed_status, observed_git FROM workspaces WHERE id = ?`)
      .get(PROJECT_A_REPOSITORY_WORKSPACE_ID);

    expect(row).toEqual({
      observed_status: null,
      observed_git: null,
    });
  });

  it('normalizes legacy workspace host fields and backfills parent_id', async () => {
    fixture = await openFixture('pre-0029');

    const remoteWorktree = fixture.sqlite
      .prepare(
        `SELECT location, ssh_connection_id, kind, parent_id
         FROM workspaces
         WHERE id = ?`
      )
      .get(TYPE_ONLY_REMOTE_WORKSPACE_ID);

    expect(remoteWorktree).toEqual({
      location: 'remote',
      ssh_connection_id: SSH_CONNECTION_ID,
      kind: 'worktree',
      parent_id: PROJECT_REMOTE_REPOSITORY_WORKSPACE_ID,
    });

    const localWorktree = fixture.sqlite
      .prepare(`SELECT parent_id FROM workspaces WHERE id = ?`)
      .get(TASK_A1_WORKSPACE_ID);

    expect(localWorktree).toEqual({ parent_id: PROJECT_A_REPOSITORY_WORKSPACE_ID });
  });

  it('deduplicates workspace identities without dangling task references', async () => {
    fixture = await openFixture('pre-0029');

    const loser = fixture.sqlite
      .prepare(`SELECT untracked_at FROM workspaces WHERE id = ?`)
      .get(DUPLICATE_DROP_WORKSPACE_ID) as { untracked_at: string | null };
    const task = fixture.sqlite
      .prepare(`SELECT workspace_id FROM tasks WHERE id = 'aaaa0002-0000-0000-0000-000000000000'`)
      .get();

    expect(loser.untracked_at).not.toBeNull();
    expect(task).toEqual({ workspace_id: DUPLICATE_KEEP_WORKSPACE_ID });
  });

  it('creates registry identity indexes and project repository uniqueness', async () => {
    fixture = await openFixture('pre-0029');

    const workspaceIndexes = fixture.sqlite.prepare(`PRAGMA index_list('workspaces')`).all() as {
      name: string;
      partial: number;
      unique: number;
    }[];
    const projectIndexes = fixture.sqlite.prepare(`PRAGMA index_list('projects')`).all() as {
      name: string;
      partial: number;
      unique: number;
    }[];

    expect(workspaceIndexes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ name: 'idx_workspaces_local_path', partial: 1, unique: 1 }),
        expect.objectContaining({ name: 'idx_workspaces_remote_path', partial: 1, unique: 1 }),
        expect.objectContaining({ name: 'idx_workspaces_parent_id', unique: 0 }),
      ])
    );
    expect(projectIndexes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          name: 'idx_projects_repository_workspace_id',
          partial: 1,
          unique: 1,
        }),
      ])
    );

    expect(() =>
      fixture.sqlite
        .prepare(
          `INSERT INTO workspaces (id, type, location, path)
           VALUES ('duplicate-local-index', 'local', 'local', ?)`
        )
        .run('/home/dev/projects/emdash-worktrees/duplicate')
    ).toThrow(/UNIQUE constraint failed/);

    expect(() =>
      fixture.sqlite
        .prepare(
          `INSERT INTO workspaces (id, type, location, ssh_connection_id, path)
           VALUES ('duplicate-remote-index', 'project-ssh', 'remote', ?, ?)`
        )
        .run(SSH_CONNECTION_ID, '/srv/repos/remote-api-worktrees/type-only')
    ).toThrow(/UNIQUE constraint failed/);

    fixture.sqlite
      .prepare(
        `INSERT INTO workspaces (id, type, location, path)
         VALUES ('soft-delete-before', 'local', 'local', '/tmp/reusable')`
      )
      .run();
    fixture.sqlite
      .prepare(
        `UPDATE workspaces SET untracked_at = CURRENT_TIMESTAMP WHERE id = 'soft-delete-before'`
      )
      .run();
    expect(() =>
      fixture.sqlite
        .prepare(
          `INSERT INTO workspaces (id, type, location, path)
           VALUES ('soft-delete-after', 'local', 'local', '/tmp/reusable')`
        )
        .run()
    ).not.toThrow();

    expect(() =>
      fixture.sqlite
        .prepare(
          `INSERT INTO projects (id, name, repository_workspace_id)
           VALUES ('duplicate-repo-project', 'Duplicate Repo', ?)`
        )
        .run(PROJECT_A_REPOSITORY_WORKSPACE_ID)
    ).toThrow(/UNIQUE constraint failed/);
  });
});
