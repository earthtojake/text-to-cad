import { encryptedAppSecretsStore } from '@main/host/secrets/encrypted-app-secrets-store';
import { toPlaintextSecretStore } from '@main/host/secrets/plaintext-secret-store';
import { ProviderAccountRegistry } from './provider-account-registry';

export const providerAccountRegistry = new ProviderAccountRegistry(
  undefined,
  toPlaintextSecretStore(encryptedAppSecretsStore)
);
