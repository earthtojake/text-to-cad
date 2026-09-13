/**
 * Test utilities for provider-account DB integration tests (main-db project).
 *
 * Opens a real SQLite fixture and wires a real ProviderAccountRegistry to it.
 * Only the secret store is in-memory, because encryptedAppSecretsStore depends
 * on Electron safeStorage which is unavailable under plain Node.
 */

import {
  ProviderAccountRegistry,
  type ProviderAccountSecretStore,
} from '@main/core/provider-accounts/provider-account-registry';
import { openFixture, type FixtureDb } from './db';

export class InMemorySecretStore implements ProviderAccountSecretStore {
  readonly secrets = new Map<string, string>();

  async getSecret(key: string): Promise<string | null> {
    return this.secrets.get(key) ?? null;
  }

  async setSecret(key: string, value: string): Promise<void> {
    this.secrets.set(key, value);
  }

  async deleteSecret(key: string): Promise<void> {
    this.secrets.delete(key);
  }
}

export type RegistryFixture = FixtureDb & {
  registry: ProviderAccountRegistry;
  secretStore: InMemorySecretStore;
};

/** Open a fixture database with a real ProviderAccountRegistry on top of it. */
export async function openRegistryFixture(
  name: Parameters<typeof openFixture>[0] = 'empty'
): Promise<RegistryFixture> {
  const fixture = await openFixture(name);
  const secretStore = new InMemorySecretStore();
  const registry = new ProviderAccountRegistry(fixture.db, secretStore);
  return { ...fixture, registry, secretStore };
}
