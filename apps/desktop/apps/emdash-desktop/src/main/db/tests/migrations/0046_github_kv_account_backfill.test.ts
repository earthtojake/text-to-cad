import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

/**
 * 0046 retires the recurring GitHub KV-account startup backfill as a run-once
 * data migration (spec: github-git-settings §10, invariant 7).
 *
 * The pre-0046 fixture carries the legacy `githubAccounts` KV namespace with
 * three valid accounts (one of which already exists as a provider_accounts
 * row and is the current default), two invalid entries, a default pointer at
 * a KV-only account, a tombstone key, and one unrelated KV row.
 */

type ProviderAccountRow = {
  id: string;
  account_id: string;
  credential_ref: string;
  is_default: number;
  meta: string;
  created_at: number;
  updated_at: number;
};

describe('0046 github kv account backfill', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('pre-0046');
  });

  afterEach(() => {
    fixture?.close();
  });

  function githubRows(): ProviderAccountRow[] {
    return fixture.sqlite
      .prepare(
        `SELECT id, account_id, credential_ref, is_default, meta, created_at, updated_at
         FROM provider_accounts WHERE provider_id = 'github' ORDER BY account_id`
      )
      .all() as ProviderAccountRow[];
  }

  it('imports valid KV accounts and skips entries without a usable id', () => {
    const rows = githubRows();
    expect(rows.map((row) => row.account_id)).toEqual(['acc-alpha', 'acc-beta', 'acc-gamma']);

    const alpha = rows.find((row) => row.account_id === 'acc-alpha');
    expect(alpha?.credential_ref).toBe('github-account-token:acc-alpha');
    expect(JSON.parse(alpha?.meta ?? '{}')).toEqual({
      version: '1',
      providerAccountId: '100',
      host: 'github.com',
      login: 'alpha',
      avatarUrl: 'https://avatars.example/alpha.png',
      credentialSource: 'emdash_oauth',
    });
  });

  it('omits absent legacy fields from meta instead of writing nulls', () => {
    const gamma = githubRows().find((row) => row.account_id === 'acc-gamma');
    const meta = JSON.parse(gamma?.meta ?? '{}') as Record<string, unknown>;
    expect(meta).toEqual({
      version: '1',
      providerAccountId: '300',
      host: 'ghe.example.com',
      login: 'gamma',
    });
    expect(Object.hasOwn(meta, 'avatarUrl')).toBe(false);
    expect(Object.hasOwn(meta, 'credentialSource')).toBe(false);
  });

  it('updates the existing row in place, preserving id, credentialRef, and createdAt', () => {
    const beta = githubRows().find((row) => row.account_id === 'acc-beta');
    expect(beta?.id).toBe('row-beta');
    expect(beta?.credential_ref).toBe('github-account-token:acc-beta');
    expect(beta?.created_at).toBe(1700000000000);
    expect(beta?.updated_at).toBeGreaterThan(1700000000000);

    const meta = JSON.parse(beta?.meta ?? '{}') as Record<string, unknown>;
    expect(meta.login).toBe('beta-new');
    expect(meta.credentialSource).toBe('cli');
  });

  it('moves the default to the legacy pointer target, keeping exactly one default', () => {
    const rows = githubRows();
    const defaults = rows.filter((row) => row.is_default === 1);
    expect(defaults.map((row) => row.account_id)).toEqual(['acc-alpha']);
  });

  it('deletes the githubAccounts namespace and keeps unrelated KV rows', () => {
    const legacyKeys = fixture.sqlite
      .prepare(`SELECT count(*) AS n FROM kv WHERE key LIKE 'githubAccounts:%'`)
      .get() as { n: number };
    expect(legacyKeys.n).toBe(0);

    const unrelated = fixture.sqlite
      .prepare(`SELECT value FROM kv WHERE key = 'telemetry:distinctId'`)
      .get() as { value: string } | undefined;
    expect(unrelated?.value).toBe('"fixture-distinct-id"');
  });

  it('no-ops on a fresh database', async () => {
    const fresh = await openFixture('empty');
    try {
      const accounts = fresh.sqlite
        .prepare(`SELECT count(*) AS n FROM provider_accounts`)
        .get() as { n: number };
      expect(accounts.n).toBe(0);
    } finally {
      fresh.close();
    }
  });
});
