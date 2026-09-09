import type { Secret } from '@emdash/shared';
import type { SecretStore } from '@core/primitives/secrets/api/secret-store';

/**
 * Stores and retrieves SSH passwords and passphrases as `Secret`-typed values.
 * Plaintext never surfaces here: values arrive wrapped, pass through the
 * Secret-typed store, and are disclosed only at the ssh2 connect-config
 * assembly (`connect/ssh-connect-auth.ts`).
 */
export class SshCredentialService {
  constructor(private readonly secrets: SecretStore) {}

  private passwordSecretKey(connectionId: string): string {
    return `ssh:${connectionId}:password`;
  }

  private passphraseSecretKey(connectionId: string): string {
    return `ssh:${connectionId}:passphrase`;
  }

  async storePassword(connectionId: string, password: Secret<string>): Promise<void> {
    try {
      await this.secrets.setSecret(this.passwordSecretKey(connectionId), password);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to store password for connection ${connectionId}: ${message}`);
    }
  }

  async getPassword(connectionId: string): Promise<Secret<string> | null> {
    try {
      return await this.secrets.getSecret(this.passwordSecretKey(connectionId));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to retrieve password for connection ${connectionId}: ${message}`);
    }
  }

  async deletePassword(connectionId: string): Promise<void> {
    try {
      await this.secrets.deleteSecret(this.passwordSecretKey(connectionId));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to delete password for connection ${connectionId}: ${message}`);
    }
  }

  async hasPassword(connectionId: string): Promise<boolean> {
    try {
      const credential = await this.secrets.getSecret(this.passwordSecretKey(connectionId));
      return credential !== null;
    } catch {
      return false;
    }
  }

  async storePassphrase(connectionId: string, passphrase: Secret<string>): Promise<void> {
    try {
      await this.secrets.setSecret(this.passphraseSecretKey(connectionId), passphrase);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to store passphrase for connection ${connectionId}: ${message}`);
    }
  }

  async getPassphrase(connectionId: string): Promise<Secret<string> | null> {
    try {
      return await this.secrets.getSecret(this.passphraseSecretKey(connectionId));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to retrieve passphrase for connection ${connectionId}: ${message}`);
    }
  }

  async deletePassphrase(connectionId: string): Promise<void> {
    try {
      await this.secrets.deleteSecret(this.passphraseSecretKey(connectionId));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Failed to delete passphrase for connection ${connectionId}: ${message}`);
    }
  }

  async hasPassphrase(connectionId: string): Promise<boolean> {
    try {
      const credential = await this.secrets.getSecret(this.passphraseSecretKey(connectionId));
      return credential !== null;
    } catch {
      return false;
    }
  }

  async storeCredentials(
    connectionId: string,
    credentials: { password?: Secret<string>; passphrase?: Secret<string> }
  ): Promise<void> {
    const operations: Promise<void>[] = [];
    if (credentials.password) {
      operations.push(this.storePassword(connectionId, credentials.password));
    }
    if (credentials.passphrase) {
      operations.push(this.storePassphrase(connectionId, credentials.passphrase));
    }
    if (operations.length > 0) {
      await Promise.all(operations);
    }
  }

  async deleteAllCredentials(connectionId: string): Promise<void> {
    await Promise.all([
      this.deletePassword(connectionId).catch(() => {}),
      this.deletePassphrase(connectionId).catch(() => {}),
    ]);
  }
}
