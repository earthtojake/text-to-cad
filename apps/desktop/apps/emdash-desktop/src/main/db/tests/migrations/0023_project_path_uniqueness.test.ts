import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

/**
 * 0023 introduced host-scoped path uniqueness on the projects table. The
 * retirement train (0032-0034) later moved project identity onto repository
 * workspace rows and dropped the project path columns and indexes, so a
 * pre-0023 database migrated to head must land on the workspace-side model.
 */
describe('0023 project path uniqueness (superseded by the retirement train)', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('migrates pre-0023 databases to the workspace-owned identity model', async () => {
    fixture = await openFixture('pre-0023');

    const projectIndexes = fixture.sqlite.prepare(`PRAGMA index_list('projects')`).all() as {
      name: string;
    }[];
    const indexNames = projectIndexes.map(({ name }) => name);
    expect(indexNames).not.toContain('idx_projects_path');
    expect(indexNames).not.toContain('idx_projects_local_path');
    expect(indexNames).not.toContain('idx_projects_remote_path');
    expect(indexNames).toContain('idx_projects_repository_workspace_id');

    const projectColumns = fixture.sqlite.prepare(`PRAGMA table_info('projects')`).all() as {
      name: string;
    }[];
    const columnNames = projectColumns.map(({ name }) => name);
    expect(columnNames).not.toContain('path');
    expect(columnNames).not.toContain('workspace_provider');
    expect(columnNames).not.toContain('ssh_connection_id');
  });

  it('enforces host-scoped path uniqueness on workspaces at head', async () => {
    fixture = await openFixture('pre-0023');

    const insertWorkspace = fixture.sqlite.prepare(
      `INSERT INTO workspaces (id, type, kind, location, ssh_connection_id, path)
       VALUES (?, ?, 'repository', ?, ?, '/srv/repos/emdash')`
    );
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, username) VALUES ('connection-a', 'A', 'host-a', 'test')`
      )
      .run();

    insertWorkspace.run('local-repo', 'local', 'local', null);
    insertWorkspace.run('remote-repo', 'project-ssh', 'remote', 'connection-a');

    expect(() => insertWorkspace.run('duplicate-local', 'local', 'local', null)).toThrow(
      /UNIQUE constraint failed/
    );
    expect(() =>
      insertWorkspace.run('duplicate-remote', 'project-ssh', 'remote', 'connection-a')
    ).toThrow(/UNIQUE constraint failed/);

    // Untracked rows leave the uniqueness partition.
    fixture.sqlite
      .prepare(`UPDATE workspaces SET untracked_at = CURRENT_TIMESTAMP WHERE id = 'local-repo'`)
      .run();
    expect(() => insertWorkspace.run('local-repo-again', 'local', 'local', null)).not.toThrow();
  });
});
