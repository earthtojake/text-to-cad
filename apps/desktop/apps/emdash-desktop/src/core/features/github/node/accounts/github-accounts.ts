import type { GitHubAccountSummary, GitHubCredentialSource } from '@core/primitives/github/api';
import type { ProviderAccountIdentity } from '@core/primitives/provider-accounts/api';
import { normalizeRepositoryHost } from '@core/primitives/repository/api';
import type {
  ProviderAccount,
  ProviderAccountStore,
} from '@core/services/provider-accounts/api/provider-account-store';

export const GITHUB_PROVIDER_ID = 'github';

export type GitHubProviderAccount = ProviderAccountIdentity & { providerId: 'github' };

/** Flat GitHub-shaped view over a generic provider account row. */
export type GitHubAccount = Omit<GitHubAccountSummary, 'isDefault'> & {
  providerAccountId: string;
  connectedAt: number;
  updatedAt: number;
};

export type GitHubAccountUpsert = {
  accessToken: string;
  credentialSource: GitHubCredentialSource;
  providerAccount: GitHubProviderAccount;
};

export type GitHubAccountUpsertResult = {
  account: GitHubAccount;
  status: 'created' | 'updated';
};

/** The generic registry surface GitHub code depends on. */
export type GitHubAccountStore = Pick<
  ProviderAccountStore,
  | 'upsertAccount'
  | 'listAccounts'
  | 'getAccount'
  | 'getDefaultAccountId'
  | 'setDefaultAccount'
  | 'resolveSecret'
  | 'removeAccount'
>;

export function normalizeGitHubHost(host: string): string {
  return normalizeRepositoryHost(host) || 'github.com';
}

/**
 * The connected GitHub accounts as the shared summary shape (with the store's
 * default flag) — the account input every blessed-resolver call site uses.
 */
export async function listGitHubAccountSummaries(
  store: Pick<GitHubAccountStore, 'listAccounts' | 'getDefaultAccountId'>
): Promise<GitHubAccountSummary[]> {
  const [accounts, defaultAccountId] = await Promise.all([
    store.listAccounts(GITHUB_PROVIDER_ID),
    store.getDefaultAccountId(GITHUB_PROVIDER_ID),
  ]);
  return accounts.map(toGitHubAccount).map((account) => ({
    accountId: account.accountId,
    host: account.host,
    login: account.login,
    avatarUrl: account.avatarUrl,
    credentialSource: account.credentialSource,
    isDefault: account.accountId === defaultAccountId,
  }));
}

/** Map a generic provider account to the flat GitHub shape. */
export function toGitHubAccount(account: ProviderAccount): GitHubAccount {
  // accountId convention is `${host}:${providerAccountId}`; used as a fallback
  // for rows whose meta is missing or unreadable.
  const separator = account.accountId.lastIndexOf(':');
  const fallbackHost = separator > 0 ? account.accountId.slice(0, separator) : 'github.com';
  const fallbackProviderAccountId =
    separator > 0 ? account.accountId.slice(separator + 1) : account.accountId;

  return {
    accountId: account.accountId,
    providerAccountId: account.meta?.providerAccountId ?? fallbackProviderAccountId,
    host: account.meta?.host ?? fallbackHost,
    login: account.meta?.login ?? '',
    avatarUrl: account.meta?.avatarUrl ?? '',
    credentialSource:
      (account.meta?.credentialSource as GitHubCredentialSource | undefined) ?? 'secure_storage',
    connectedAt: account.createdAt,
    updatedAt: account.updatedAt,
  };
}

/**
 * Store a GitHub account in the generic provider account registry: constructs
 * the `${host}:${providerAccountId}` account id and maps the identity fields
 * into the generic meta blob.
 */
export async function upsertGitHubAccount(
  store: Pick<GitHubAccountStore, 'upsertAccount'>,
  input: GitHubAccountUpsert
): Promise<GitHubAccountUpsertResult> {
  const host = normalizeGitHubHost(input.providerAccount.host);
  const accountId = `${host}:${input.providerAccount.providerAccountId}`;
  const { account, status } = await store.upsertAccount({
    providerId: GITHUB_PROVIDER_ID,
    accountId,
    secret: input.accessToken,
    meta: {
      providerAccountId: input.providerAccount.providerAccountId,
      host,
      login: input.providerAccount.login,
      avatarUrl: input.providerAccount.avatarUrl,
      credentialSource: input.credentialSource,
    },
  });
  return { account: toGitHubAccount(account), status };
}
