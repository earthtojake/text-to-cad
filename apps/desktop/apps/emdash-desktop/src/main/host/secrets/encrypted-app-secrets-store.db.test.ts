import { REDACTED, secret } from '@emdash/shared';
import { openFixture, type FixtureDb } from '@tooling/utils/db';
import { eq } from 'drizzle-orm';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { appSecrets } from '@core/services/app-db/node/schema';
import { EncryptedAppSecretsStore } from './encrypted-app-secrets-store';

vi.mock('electron', () => ({ safeStorage: undefined }));

/** Reversible stand-in for Electron safeStorage, unavailable under plain Node. */
const fakeSafeStorage = {
  isEncryptionAvailable: () => true,
  encryptString: (value: string) => Buffer.from(`enc:${value}`, 'utf8'),
  decryptString: (buffer: Buffer) => buffer.toString('utf8').slice('enc:'.length),
} as unknown as Electron.SafeStorage;

let fixture: FixtureDb | undefined;

async function makeStore() {
  fixture = await openFixture('empty');
  return new EncryptedAppSecretsStore(fixture.db, fakeSafeStorage, 'darwin');
}

afterEach(() => {
  fixture?.close();
  fixture = undefined;
});

describe('EncryptedAppSecretsStore', () => {
  it('round-trips a Secret-typed value intact', async () => {
    const store = await makeStore();
    await store.setSecret('test-key', secret('hunter2', 'test-key'));

    const retrieved = await store.getSecret('test-key');
    expect(retrieved?.expose()).toBe('hunter2');
  });

  it('persists only encrypted material at rest', async () => {
    const store = await makeStore();
    await store.setSecret('test-key', secret('hunter2'));

    const rows = await fixture!.db
      .select({ secret: appSecrets.secret })
      .from(appSecrets)
      .where(eq(appSecrets.key, 'test-key'));
    expect(rows[0]?.secret).toBe(Buffer.from('enc:hunter2', 'utf8').toString('base64'));
    expect(rows[0]?.secret).not.toContain('hunter2');
  });

  it('returns null for a missing key', async () => {
    const store = await makeStore();
    await expect(store.getSecret('missing')).resolves.toBeNull();
  });

  it('serializes retrieved credentials as the redacted placeholder, never plaintext', async () => {
    const store = await makeStore();
    await store.setSecret('test-key', secret('hunter2'));
    const retrieved = await store.getSecret('test-key');

    const carrying = { key: 'test-key', value: retrieved };
    expect(JSON.stringify(carrying)).not.toContain('hunter2');
    expect(JSON.stringify(carrying)).toContain(REDACTED);
  });

  it('deletes stored secrets', async () => {
    const store = await makeStore();
    await store.setSecret('test-key', secret('hunter2'));
    await store.deleteSecret('test-key');
    await expect(store.getSecret('test-key')).resolves.toBeNull();
  });
});
