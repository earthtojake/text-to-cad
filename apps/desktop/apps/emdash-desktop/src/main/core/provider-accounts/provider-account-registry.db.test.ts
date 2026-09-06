import { openRegistryFixture, type RegistryFixture } from '@tooling/utils/provider-accounts';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { defaultCredentialRef } from './provider-account-registry';

describe('ProviderAccountRegistry', () => {
  let fixture: RegistryFixture;

  beforeEach(async () => {
    fixture = await openRegistryFixture('empty');
  });

  afterEach(() => {
    fixture?.close();
  });

  async function upsert(providerId: string, accountId: string, secret = `secret-${accountId}`) {
    return fixture.registry.upsertAccount({ providerId, accountId, secret });
  }

  it('creates an account with its secret behind the credentialRef', async () => {
    const { account, status } = await fixture.registry.upsertAccount({
      providerId: 'linear',
      accountId: 'default',
      secret: 'lin_api_123',
      meta: { displayName: 'Acme Linear' },
    });

    expect(status).toBe('created');
    expect(account).toMatchObject({
      providerId: 'linear',
      accountId: 'default',
      credentialRef: defaultCredentialRef('linear', 'default'),
      isDefault: true,
      meta: { version: '1', displayName: 'Acme Linear' },
    });
    expect(fixture.secretStore.secrets.get(account.credentialRef)).toBe('lin_api_123');
    await expect(fixture.registry.resolveSecret('linear', 'default')).resolves.toBe('lin_api_123');
  });

  it('updates an existing account instead of duplicating it', async () => {
    await upsert('github', 'github.com:42', 'old-token');
    const { account, status } = await fixture.registry.upsertAccount({
      providerId: 'github',
      accountId: 'github.com:42',
      secret: 'new-token',
      meta: { login: 'mona' },
    });

    expect(status).toBe('updated');
    expect(account.meta).toMatchObject({ login: 'mona' });
    await expect(fixture.registry.listAccounts('github')).resolves.toHaveLength(1);
    await expect(fixture.registry.resolveSecret('github', 'github.com:42')).resolves.toBe(
      'new-token'
    );
  });

  it('keeps the stored secret and meta on a partial update', async () => {
    await fixture.registry.upsertAccount({
      providerId: 'github',
      accountId: 'github.com:42',
      secret: 'token',
      meta: { login: 'mona' },
    });

    const { account } = await fixture.registry.upsertAccount({
      providerId: 'github',
      accountId: 'github.com:42',
    });

    expect(account.meta).toMatchObject({ login: 'mona' });
    await expect(fixture.registry.resolveSecret('github', 'github.com:42')).resolves.toBe('token');
  });

  it('never changes the credentialRef of an existing account', async () => {
    const { account: created } = await upsert('github', 'github.com:42');
    const { account: updated } = await fixture.registry.upsertAccount({
      providerId: 'github',
      accountId: 'github.com:42',
      credentialRef: 'some-other-ref',
      secret: 'refreshed',
    });

    expect(updated.credentialRef).toBe(created.credentialRef);
    expect(fixture.secretStore.secrets.get(created.credentialRef)).toBe('refreshed');
  });

  it('honors a credentialRef override for new accounts', async () => {
    const { account } = await fixture.registry.upsertAccount({
      providerId: 'github',
      accountId: 'github.com:42',
      credentialRef: 'github-account-token:github.com:42',
      secret: 'token',
    });

    expect(account.credentialRef).toBe('github-account-token:github.com:42');
    await expect(fixture.registry.resolveSecret('github', 'github.com:42')).resolves.toBe('token');
  });

  it('round-trips meta through the versioned JSON column', async () => {
    await fixture.registry.upsertAccount({
      providerId: 'github',
      accountId: 'github.com:42',
      secret: 'token',
      meta: {
        displayName: 'Mona Lisa',
        login: 'monalisa',
        avatarUrl: 'https://avatars.githubusercontent.com/u/42',
        host: 'github.com',
        providerAccountId: '42',
        credentialSource: 'emdash_oauth',
      },
    });

    const [account] = await fixture.registry.listAccounts('github');
    expect(account.meta).toEqual({
      version: '1',
      displayName: 'Mona Lisa',
      login: 'monalisa',
      avatarUrl: 'https://avatars.githubusercontent.com/u/42',
      host: 'github.com',
      providerAccountId: '42',
      credentialSource: 'emdash_oauth',
    });
  });

  it('makes the first account of a provider the default and keeps it on later inserts', async () => {
    await upsert('github', 'github.com:42');
    await upsert('github', 'github.com:84');

    await expect(fixture.registry.getDefaultAccountId('github')).resolves.toBe('github.com:42');
  });

  it('tracks defaults per provider independently', async () => {
    await upsert('github', 'github.com:42');
    await upsert('linear', 'default');

    await expect(fixture.registry.getDefaultAccountId('github')).resolves.toBe('github.com:42');
    await expect(fixture.registry.getDefaultAccountId('linear')).resolves.toBe('default');
  });

  it('switches the default account explicitly', async () => {
    await upsert('github', 'github.com:42');
    await upsert('github', 'github.com:84');

    const account = await fixture.registry.setDefaultAccount('github', 'github.com:84');

    expect(account).toMatchObject({ accountId: 'github.com:84', isDefault: true });
    await expect(fixture.registry.getDefaultAccountId('github')).resolves.toBe('github.com:84');
  });

  it('does not change the default for an unknown account id', async () => {
    await upsert('github', 'github.com:42');

    await expect(
      fixture.registry.setDefaultAccount('github', 'github.com:missing')
    ).resolves.toBeNull();
    await expect(fixture.registry.getDefaultAccountId('github')).resolves.toBe('github.com:42');
  });

  it('promotes the oldest surviving account when the default is removed', async () => {
    await upsert('github', 'github.com:42');
    await upsert('github', 'github.com:84');
    await upsert('github', 'github.com:168');
    await fixture.registry.setDefaultAccount('github', 'github.com:84');

    const removed = await fixture.registry.removeAccount('github', 'github.com:84');

    expect(removed).toMatchObject({ accountId: 'github.com:84' });
    await expect(fixture.registry.getDefaultAccountId('github')).resolves.toBe('github.com:42');
  });

  it('removes the secret together with the account', async () => {
    const { account } = await upsert('github', 'github.com:42', 'token');

    await fixture.registry.removeAccount('github', 'github.com:42');

    expect(fixture.secretStore.secrets.has(account.credentialRef)).toBe(false);
    await expect(fixture.registry.resolveSecret('github', 'github.com:42')).resolves.toBeNull();
    await expect(fixture.registry.listAccounts('github')).resolves.toEqual([]);
  });

  it('returns null when removing an unknown account', async () => {
    await expect(
      fixture.registry.removeAccount('github', 'github.com:missing')
    ).resolves.toBeNull();
  });

  it('reports no default when the last account is removed', async () => {
    await upsert('github', 'github.com:42');

    await fixture.registry.removeAccount('github', 'github.com:42');

    await expect(fixture.registry.getDefaultAccountId('github')).resolves.toBeNull();
  });

  it('self-heals a missing default flag to the oldest account', async () => {
    await upsert('github', 'github.com:42');
    await upsert('github', 'github.com:84');
    // Simulate a row set that lost its default marker (e.g. hand-edited DB).
    fixture.sqlite.prepare(`UPDATE provider_accounts SET is_default = 0`).run();

    await expect(fixture.registry.getDefaultAccountId('github')).resolves.toBe('github.com:42');
    const [first] = await fixture.registry.listAccounts('github');
    expect(first.isDefault).toBe(true);
  });

  it('resolves the default account secret when no account id is given', async () => {
    await upsert('github', 'github.com:42', 'default-token');
    await upsert('github', 'github.com:84', 'other-token');

    await expect(fixture.registry.resolveSecret('github')).resolves.toBe('default-token');
  });

  it('removes all accounts and secrets for a provider', async () => {
    await upsert('github', 'github.com:42');
    await upsert('github', 'github.com:84');
    await upsert('linear', 'default', 'lin-token');

    await fixture.registry.removeAllAccounts('github');

    await expect(fixture.registry.listAccounts('github')).resolves.toEqual([]);
    expect(fixture.secretStore.secrets.size).toBe(1);
    await expect(fixture.registry.resolveSecret('linear', 'default')).resolves.toBe('lin-token');
  });

  it('reports configuration status per provider', async () => {
    await expect(fixture.registry.isConfigured('github')).resolves.toBe(false);
    await upsert('github', 'github.com:42');
    await expect(fixture.registry.isConfigured('github')).resolves.toBe(true);
    await expect(fixture.registry.isConfigured('linear')).resolves.toBe(false);
  });
});
