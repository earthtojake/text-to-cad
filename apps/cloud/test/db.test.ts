import { describe, expect, it } from 'vitest';
import { createPgliteDb, isUniqueViolation, migrate } from '../server/db/index.ts';

describe('database', () => {
  it('applies the schema again without harm, and holds one active build per person', async () => {
    const db = await createPgliteDb();
    try {
      await migrate(db);
      await migrate(db);
      const now = new Date().toISOString();
      await db.query("insert into users (id, issuer, subject, created_at) values ('u', 'dev', 'u', $1)", [now]);
      const insert = (id: string, status: string) => db.query(
        `insert into builds (id, user_id, entry, pythonpath, files, dedupe_key, status, limits, created_at, updated_at)
         values ($1, 'u', '[]', '[]', '[]', 'k', $2, '{"timeoutSeconds": 1, "vcpus": 1}', $3, $3)`,
        [id, status, now],
      );
      await insert('a', 'succeeded');
      await insert('b', 'running');
      const error = await insert('c', 'queued').catch((caught) => caught);
      expect(isUniqueViolation(error, 'builds_one_active')).toBe(true);
      const { rows } = await db.transaction((tx) => tx.query<{ n: number }>('select count(*)::int as n from builds'));
      expect(rows[0].n).toBe(2);
    } finally {
      await db.close();
    }
  });
});
