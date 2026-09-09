import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

describe('0018 workspaces SSH FK migration', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('rebuilds workspaces.ssh_connection_id with ON DELETE SET NULL', async () => {
    fixture = await openFixture('pre-0018');

    const foreignKeys = fixture.sqlite.prepare(`PRAGMA foreign_key_list(workspaces)`).all() as {
      from: string;
      on_delete: string;
      table: string;
    }[];

    const sshConnectionFk = foreignKeys.find(
      (fk) => fk.from === 'ssh_connection_id' && fk.table === 'ssh_connections'
    );

    expect(sshConnectionFk?.on_delete).toBe('SET NULL');
  });

  it('clears remote workspace references when an SSH connection is deleted', async () => {
    fixture = await openFixture('pre-0018');

    fixture.sqlite.exec(`
      INSERT INTO ssh_connections (id, name, host, port, username, auth_type, use_agent)
      VALUES ('ssh-1', 'Existing SSH', 'example.com', 22, 'jona', 'agent', 1);

      INSERT INTO workspaces (id, type, kind, location, ssh_connection_id, path)
      VALUES (
        'workspace-root-1',
        'project-ssh',
        'repository',
        'remote',
        'ssh-1',
        '/repo'
      );

      DELETE FROM ssh_connections WHERE id = 'ssh-1';
    `);

    const row = fixture.sqlite
      .prepare(`SELECT ssh_connection_id FROM workspaces WHERE id = 'workspace-root-1'`)
      .get() as { ssh_connection_id: string | null };

    expect(row.ssh_connection_id).toBeNull();
  });
});
