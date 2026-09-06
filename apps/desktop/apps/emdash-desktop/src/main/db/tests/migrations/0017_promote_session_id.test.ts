import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';

/**
 * Tests for the 0017 data migration which promotes config.providerSessionId into
 * the conversations session-id column and removes the field from the config blob.
 *
 * Since this is a pure data migration (no schema change) the tests insert rows
 * representing the pre-migration shape and verify the migration SQL transforms
 * them correctly. The 0035-0037 conversation-registry train later renames
 * provider_session_id to provider_provider_session_id, so the replayed SQL and assertions target
 * the current column name.
 */
describe('0017 promote provider_session_id migration', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  function insertProject(sqlite: typeof fixture.sqlite, id: string) {
    sqlite
      .prepare(`INSERT OR IGNORE INTO projects (id, name) VALUES (?, ?)`)
      .run(id, `project-${id}`);
  }

  function insertTask(sqlite: typeof fixture.sqlite, id: string, projectId: string) {
    sqlite
      .prepare(`INSERT OR IGNORE INTO tasks (id, project_id, name, status) VALUES (?, ?, ?, ?)`)
      .run(id, projectId, `task-${id}`, 'running');
  }

  function applyMigration(sqlite: typeof fixture.sqlite) {
    sqlite
      .prepare(
        `UPDATE conversations
         SET provider_session_id = json_extract(config, '$.providerSessionId')
         WHERE json_extract(config, '$.providerSessionId') IS NOT NULL`
      )
      .run();
    sqlite
      .prepare(
        `UPDATE conversations
         SET config = json_remove(config, '$.providerSessionId')
         WHERE json_extract(config, '$.providerSessionId') IS NOT NULL`
      )
      .run();
  }

  it('overwrites provider_session_id with config.providerSessionId when present (Droid PTY row)', async () => {
    fixture = await openFixture('pre-0017');
    insertProject(fixture.sqlite, 'p1');
    insertTask(fixture.sqlite, 't1', 'p1');

    const convId = 'conv-droid';
    const nativeId = '019c95f6-cd96-7812-ba15-574286674599';

    fixture.sqlite
      .prepare(
        `INSERT INTO conversations (id, project_id, task_id, title, provider_session_id, config)
         VALUES (?, 'p1', 't1', 'test', ?, ?)`
      )
      .run(convId, convId, JSON.stringify({ providerSessionId: nativeId, model: 'gpt-4' }));

    applyMigration(fixture.sqlite);

    const row = fixture.sqlite
      .prepare(`SELECT provider_session_id, config FROM conversations WHERE id = ?`)
      .get(convId) as { provider_session_id: string; config: string };

    expect(row.provider_session_id).toBe(nativeId);
    expect(JSON.parse(row.config).providerSessionId).toBeUndefined();
    expect(JSON.parse(row.config).model).toBe('gpt-4');
  });

  it('leaves provider_session_id unchanged for rows without config.providerSessionId', async () => {
    fixture = await openFixture('pre-0017');
    insertProject(fixture.sqlite, 'p2');
    insertTask(fixture.sqlite, 't2', 'p2');

    const convId = 'conv-no-native';
    fixture.sqlite
      .prepare(
        `INSERT INTO conversations (id, project_id, task_id, title, provider_session_id, config)
         VALUES (?, 'p2', 't2', 'test', ?, ?)`
      )
      .run(convId, convId, JSON.stringify({ model: 'claude' }));

    applyMigration(fixture.sqlite);

    const row = fixture.sqlite
      .prepare(`SELECT provider_session_id FROM conversations WHERE id = ?`)
      .get(convId) as { provider_session_id: string };

    expect(row.provider_session_id).toBe(convId);
  });

  it('leaves rows with null provider_session_id (ACP, not yet spawned) with null after migration', async () => {
    fixture = await openFixture('pre-0017');
    insertProject(fixture.sqlite, 'p3');
    insertTask(fixture.sqlite, 't3', 'p3');

    const convId = 'conv-acp-unspawned';
    fixture.sqlite
      .prepare(
        `INSERT INTO conversations (id, project_id, task_id, title, provider_session_id, config)
         VALUES (?, 'p3', 't3', 'test', NULL, ?)`
      )
      .run(convId, JSON.stringify({ model: 'claude' }));

    applyMigration(fixture.sqlite);

    const row = fixture.sqlite
      .prepare(`SELECT provider_session_id FROM conversations WHERE id = ?`)
      .get(convId) as { provider_session_id: string | null };

    expect(row.provider_session_id).toBeNull();
  });
});
