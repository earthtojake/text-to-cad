import type { GitHubTokenSource, GitHubUser } from '@core/primitives/github/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { AppDbKeyValueStore } from '@core/services/app-db/node/key-value-store';
import {
  upsertGitHubAccount,
  type GitHubAccount,
  type GitHubAccountStore,
} from './github-accounts';

type LegacyGitHubTokenMigrationStore = {
  getStoredTokenRecord(): Promise<{
    token: string;
    source: Exclude<GitHubTokenSource, null> | null;
  } | null>;
  clearStoredToken(): Promise<void>;
};

type GitHubIdentityClient = {
  getAuthenticatedUser(token: string, host?: string): Promise<GitHubUser | null>;
};

type ImportFlags = { completedAt: number };

export type GitHubLegacyTokenImportResult =
  | { status: 'already-completed' }
  | { status: 'no-legacy-token' }
  | { status: 'imported'; account: GitHubAccount }
  /** Token exists but its GitHub identity could not be resolved; retried next launch. */
  | { status: 'retry' };

function credentialSource(source: GitHubTokenSource) {
  return source ?? 'secure_storage';
}

function providerAccountFromUser(user: GitHubUser) {
  return {
    providerId: 'github' as const,
    providerAccountId: String(user.id),
    host: 'github.com',
    login: user.login,
    avatarUrl: user.avatar_url,
  };
}

/**
 * Run-once upgrade step (spec: github-git-settings §10, invariant 7): imports
 * the pre-account single GitHub token (`emdash-github-token` in secret
 * storage) into a provider account, then clears the legacy secret. Secret
 * storage is a non-DB source, so this cannot be a Drizzle data migration; the
 * done-flag lives in the app DB `kv` table instead
 * (`github-legacy-token-import:completedAt`).
 *
 * The flag is only written on success: fresh installs and already-migrated
 * databases complete immediately on their first launch (no legacy token), and
 * a failed identity lookup leaves the flag unset so the step retries on the
 * next launch. Once the flag is set, later launches read one KV row and never
 * probe secret storage again.
 */
export class GitHubLegacyTokenImportStep {
  private readonly flags: AppDbKeyValueStore<ImportFlags>;

  constructor(
    db: AppDb,
    private readonly accountStore: Pick<GitHubAccountStore, 'upsertAccount'>,
    private readonly legacyTokenStore: LegacyGitHubTokenMigrationStore,
    private readonly identityClient: GitHubIdentityClient
  ) {
    this.flags = new AppDbKeyValueStore<ImportFlags>(db, 'github-legacy-token-import');
  }

  async run(): Promise<GitHubLegacyTokenImportResult> {
    if ((await this.flags.get('completedAt')) !== null) return { status: 'already-completed' };

    const tokenRecord = await this.legacyTokenStore.getStoredTokenRecord();
    if (!tokenRecord) {
      await this.flags.setOrThrow('completedAt', Date.now());
      return { status: 'no-legacy-token' };
    }

    const user = await this.identityClient.getAuthenticatedUser(tokenRecord.token, 'github.com');
    if (!user) return { status: 'retry' };

    const { account } = await upsertGitHubAccount(this.accountStore, {
      accessToken: tokenRecord.token,
      credentialSource: credentialSource(tokenRecord.source),
      providerAccount: providerAccountFromUser(user),
    });
    await this.legacyTokenStore.clearStoredToken();
    await this.flags.setOrThrow('completedAt', Date.now());
    return { status: 'imported', account };
  }
}
