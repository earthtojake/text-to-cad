import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';
import { providerAccounts } from '@core/services/app-db/node/schema';

describe('0019_provider_accounts', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('creates the provider_accounts table on top of the pre-0019 fixture', async () => {
    fixture = await openFixture('pre-0019');

    const tables = fixture.sqlite
      .prepare(`SELECT name FROM sqlite_master WHERE type='table' AND name='provider_accounts'`)
      .all() as { name: string }[];
    expect(tables).toHaveLength(1);

    const rows = await fixture.db.select().from(providerAccounts);
    expect(rows).toHaveLength(0);
  });

  it('enforces unique (provider_id, account_id)', async () => {
    fixture = await openFixture('pre-0019');

    const insert = fixture.sqlite.prepare(
      `INSERT INTO provider_accounts
         (id, provider_id, account_id, credential_ref, is_default, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    );
    insert.run('a', 'github', 'github.com:1', 'ref-1', 1, 1, 1);
    expect(() => insert.run('b', 'github', 'github.com:1', 'ref-2', 0, 2, 2)).toThrow(
      /UNIQUE constraint failed/
    );
  });

  it('allows at most one default account per provider', async () => {
    fixture = await openFixture('pre-0019');

    const insert = fixture.sqlite.prepare(
      `INSERT INTO provider_accounts
         (id, provider_id, account_id, credential_ref, is_default, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    );
    insert.run('a', 'github', 'github.com:1', 'ref-1', 1, 1, 1);
    // Second non-default account for the same provider is fine.
    insert.run('b', 'github', 'github.com:2', 'ref-2', 0, 2, 2);
    // Default for a different provider is fine.
    insert.run('c', 'linear', 'default', 'ref-3', 1, 3, 3);
    // Second default for the same provider violates the partial unique index.
    expect(() => insert.run('d', 'github', 'github.com:3', 'ref-4', 1, 4, 4)).toThrow(
      /UNIQUE constraint failed/
    );
  });
});
