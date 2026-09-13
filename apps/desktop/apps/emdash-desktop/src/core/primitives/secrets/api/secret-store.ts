import type { Secret } from '@emdash/shared';

/**
 * Secret-typed key/value storage for credential material. Values stay wrapped
 * in `Secret` end-to-end; plaintext is disclosed via `.expose()` only at true
 * boundaries (safeStorage/keychain writes, ssh2 connect configuration, wire
 * serialization edges).
 */
export interface SecretStore {
  getSecret(key: string): Promise<Secret<string> | null>;
  setSecret(key: string, secret: Secret<string>): Promise<void>;
  deleteSecret(key: string): Promise<void>;
}

/**
 * String-typed view of a secret store for consumers that have not yet
 * migrated to `Secret` (provider accounts, integrations, account session).
 * New code should depend on `SecretStore` and keep values wrapped.
 */
export interface PlaintextSecretStore {
  getSecret(key: string): Promise<string | null>;
  setSecret(key: string, secret: string): Promise<void>;
  deleteSecret(key: string): Promise<void>;
}
