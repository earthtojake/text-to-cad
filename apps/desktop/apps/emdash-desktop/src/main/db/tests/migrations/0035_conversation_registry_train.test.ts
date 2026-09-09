import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

/**
 * The conversation-registry migration train (0035 column additions, 0036
 * observation seeds, 0037 drops + link relaxation) reshapes the client
 * conversations table into the conversation registry (spec §10.2). The
 * pre-0035 fixture carries two legacy conversations — one with a session id,
 * a last-interacted timestamp, and a vestigial messages row.
 */

const CONV_WITH_SESSION_ID = 'cccc0001-0000-0000-0000-000000000000';
const CONV_WITHOUT_SESSION_ID = 'cccc0002-0000-0000-0000-000000000000';
const TASK_A1_WORKSPACE_PATH = '/home/dev/projects/emdash-worktrees/feat-workspace-db';

describe('0035-0037 conversation registry migration train', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('pre-0035');
  });

  afterEach(() => {
    fixture?.close();
  });

  it('renames the provider handle and activity timestamp into observation columns', () => {
    const row = fixture.sqlite
      .prepare(
        `SELECT provider_session_id, last_session_activity_at FROM conversations WHERE id = ?`
      )
      .get(CONV_WITH_SESSION_ID) as {
      provider_session_id: string | null;
      last_session_activity_at: string | null;
    };
    expect(row.provider_session_id).toBe('provider-session-a1');
    expect(row.last_session_activity_at).toBe('2026-07-30 10:00:00');

    const bare = fixture.sqlite
      .prepare(
        `SELECT provider_session_id, last_session_activity_at FROM conversations WHERE id = ?`
      )
      .get(CONV_WITHOUT_SESSION_ID) as {
      provider_session_id: string | null;
      last_session_activity_at: string | null;
    };
    expect(bare.provider_session_id).toBeNull();
    expect(bare.last_session_activity_at).toBeNull();
  });

  it('seeds every pre-existing row as a present, just-observed registered record', () => {
    const rows = fixture.sqlite
      .prepare(
        `SELECT observed_status, last_observed_at, updated_at, origin, untracked_at
         FROM conversations`
      )
      .all() as Array<{
      observed_status: string;
      last_observed_at: string;
      updated_at: string;
      origin: string;
      untracked_at: string | null;
    }>;
    expect(rows).toHaveLength(2);
    for (const row of rows) {
      expect(row.observed_status).toBe('present');
      expect(row.last_observed_at).toBe(row.updated_at);
      expect(row.origin).toBe('registered');
      expect(row.untracked_at).toBeNull();
    }
  });

  it('seeds source host identity from the project repository row and paths from the task workspace', () => {
    const row = fixture.sqlite
      .prepare(
        `SELECT location, ssh_connection_id, workspace_path, cwd FROM conversations WHERE id = ?`
      )
      .get(CONV_WITH_SESSION_ID) as {
      location: string;
      ssh_connection_id: string | null;
      workspace_path: string | null;
      cwd: string | null;
    };
    expect(row.location).toBe('local');
    expect(row.ssh_connection_id).toBeNull();
    expect(row.workspace_path).toBe(TASK_A1_WORKSPACE_PATH);
    expect(row.cwd).toBe(TASK_A1_WORKSPACE_PATH);
  });

  it('drops the legacy columns and relaxes the task/project links to nullable', () => {
    const columns = fixture.sqlite.prepare(`PRAGMA table_info('conversations')`).all() as Array<{
      name: string;
      notnull: number;
    }>;
    const names = columns.map((column) => column.name);
    expect(names).not.toContain('session_id');
    expect(names).not.toContain('last_interacted_at');
    expect(names).toContain('provider_session_id');
    expect(names).toContain('last_session_activity_at');
    expect(names).toContain('id_regime');

    const byName = new Map(columns.map((column) => [column.name, column]));
    expect(byName.get('project_id')?.notnull).toBe(0);
    expect(byName.get('task_id')?.notnull).toBe(0);
    expect(byName.get('title')?.notnull).toBe(1);
    expect(byName.get('origin')?.notnull).toBe(1);
  });

  it('drops the vestigial messages table without cascading into surviving rows', () => {
    const tables = (
      fixture.sqlite.prepare(`SELECT name FROM sqlite_master WHERE type = 'table'`).all() as Array<{
        name: string;
      }>
    ).map((table) => table.name);
    expect(tables).not.toContain('messages');

    // The conversations recreate in 0037 must not cascade: annotations survive.
    const links = fixture.sqlite
      .prepare(
        `SELECT task_id, project_id, is_initial_conversation FROM conversations WHERE id = ?`
      )
      .get(CONV_WITH_SESSION_ID) as {
      task_id: string | null;
      project_id: string | null;
      is_initial_conversation: number;
    };
    expect(links.task_id).not.toBeNull();
    expect(links.project_id).not.toBeNull();
    expect(links.is_initial_conversation).toBe(1);

    const violations = fixture.sqlite.prepare(`PRAGMA foreign_key_check`).all();
    expect(violations).toEqual([]);
  });
});
