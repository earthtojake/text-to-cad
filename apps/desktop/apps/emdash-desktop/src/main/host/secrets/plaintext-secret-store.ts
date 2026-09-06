import { secret, type Secret } from '@emdash/shared';
import type { PlaintextSecretStore, SecretStore } from '@core/primitives/secrets/api/secret-store';

/**
 * String-typed compatibility view over a Secret-typed store, for consumers
 * that have not yet migrated to `Secret` (provider accounts, integrations,
 * account session, legacy credential migrations).
 *
 * Boundary disclosure: the `.expose()` below is the documented seam between
 * Secret-typed storage and those unmigrated string flows. Do not add new
 * consumers here — depend on `SecretStore` and keep values wrapped.
 */
export function toPlaintextSecretStore(store: SecretStore): PlaintextSecretStore {
  return {
    async getSecret(key: string): Promise<string | null> {
      const value: Secret<string> | null = await store.getSecret(key);
      return value === null ? null : value.expose();
    },
    setSecret(key: string, value: string): Promise<void> {
      return store.setSecret(key, secret(value, key));
    },
    deleteSecret(key: string): Promise<void> {
      return store.deleteSecret(key);
    },
  };
}
