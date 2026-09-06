import { inspect } from 'node:util';
import { REDACTED, secret, type Secret } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import type { SecretStore } from '@core/primitives/secrets/api/secret-store';
import { SshCredentialService } from './ssh-credential-service';

class InMemorySecretStore implements SecretStore {
  readonly secrets = new Map<string, Secret<string>>();

  async getSecret(key: string): Promise<Secret<string> | null> {
    return this.secrets.get(key) ?? null;
  }

  async setSecret(key: string, value: Secret<string>): Promise<void> {
    this.secrets.set(key, value);
  }

  async deleteSecret(key: string): Promise<void> {
    this.secrets.delete(key);
  }
}

function makeService() {
  const store = new InMemorySecretStore();
  return { store, service: new SshCredentialService(store) };
}

describe('SshCredentialService', () => {
  it('round-trips a password intact', async () => {
    const { service } = makeService();
    await service.storePassword('conn-1', secret('hunter2', 'ssh-password'));

    const retrieved = await service.getPassword('conn-1');
    expect(retrieved?.expose()).toBe('hunter2');
    await expect(service.hasPassword('conn-1')).resolves.toBe(true);
  });

  it('round-trips a passphrase intact', async () => {
    const { service } = makeService();
    await service.storePassphrase('conn-1', secret('correct horse', 'ssh-passphrase'));

    const retrieved = await service.getPassphrase('conn-1');
    expect(retrieved?.expose()).toBe('correct horse');
  });

  it('stores both credentials through storeCredentials', async () => {
    const { service } = makeService();
    await service.storeCredentials('conn-1', {
      password: secret('pw'),
      passphrase: secret('pp'),
    });

    expect((await service.getPassword('conn-1'))?.expose()).toBe('pw');
    expect((await service.getPassphrase('conn-1'))?.expose()).toBe('pp');
  });

  it('returns null and false for missing credentials', async () => {
    const { service } = makeService();
    await expect(service.getPassword('unknown')).resolves.toBeNull();
    await expect(service.hasPassword('unknown')).resolves.toBe(false);
  });

  it('deleteAllCredentials removes both credentials', async () => {
    const { service } = makeService();
    await service.storeCredentials('conn-1', {
      password: secret('pw'),
      passphrase: secret('pp'),
    });
    await service.deleteAllCredentials('conn-1');

    await expect(service.getPassword('conn-1')).resolves.toBeNull();
    await expect(service.getPassphrase('conn-1')).resolves.toBeNull();
  });

  it('never leaks plaintext when a credential-carrying object is serialized or logged', async () => {
    const { service } = makeService();
    await service.storePassword('conn-1', secret('hunter2', 'ssh-password'));
    const password = await service.getPassword('conn-1');

    const carrying = { connectionId: 'conn-1', password };
    expect(JSON.stringify(carrying)).not.toContain('hunter2');
    expect(JSON.stringify(carrying)).toContain(REDACTED);
    expect(`${password}`).toBe(REDACTED);
    expect(inspect(carrying)).not.toContain('hunter2');
  });

  it('wraps store failures with the connection id', async () => {
    const failing: SecretStore = {
      getSecret: async () => {
        throw new Error('store offline');
      },
      setSecret: async () => {
        throw new Error('store offline');
      },
      deleteSecret: async () => {
        throw new Error('store offline');
      },
    };
    const service = new SshCredentialService(failing);

    await expect(service.storePassword('conn-9', secret('pw'))).rejects.toThrow(
      'Failed to store password for connection conn-9: store offline'
    );
    await expect(service.getPassphrase('conn-9')).rejects.toThrow(
      'Failed to retrieve passphrase for connection conn-9: store offline'
    );
  });
});
