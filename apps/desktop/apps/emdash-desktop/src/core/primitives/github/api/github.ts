export interface GitHubUser {
  id: number;
  login: string;
  name: string;
  email: string;
  avatar_url: string;
}

export type GitHubTokenSource = 'secure_storage' | 'cli' | 'emdash_oauth' | 'device_flow' | null;

export type GitHubCredentialSource = Exclude<GitHubTokenSource, null>;

/**
 * The one shared GitHub provider-account summary, used everywhere an account
 * is passed around (Wire DTOs, node services, resolver inputs). Derive from
 * this type instead of redeclaring the shape.
 */
export interface GitHubAccountSummary {
  /** `provider_accounts` row id. */
  accountId: string;
  host: string;
  login: string;
  avatarUrl: string;
  credentialSource: GitHubCredentialSource;
  isDefault: boolean;
}

export type GitHubAccountState = {
  connected: boolean;
  accounts: GitHubAccountSummary[];
  defaultAccountId: string | null;
};

export type GitHubSetDefaultAccountResponse =
  | { success: true; account: GitHubAccountSummary }
  | { success: false; error: string };

export type GitHubImportCliAccountsResponse =
  | { success: true; accounts: GitHubAccountSummary[]; importedAccountIds: string[] }
  | { success: false; error: string };

export type GitHubRemoveAccountResponse =
  | { success: true; accounts: GitHubAccountSummary[] }
  | { success: false; error: string };

export type GitHubAuthResponse =
  | { success: true; account: GitHubAccountSummary }
  | { success: false; error: string };

export interface GitHubRepo {
  id: number;
  name: string;
  nameWithOwner: string;
  description: string | null;
  url: string;
  cloneUrl: string;
  sshUrl: string;
  defaultBranch: string;
  isPrivate: boolean;
  updatedAt: string | null;
  language: string | null;
  stargazersCount: number;
  forksCount: number;
}

export interface GitHubOwner {
  login: string;
  type: 'User' | 'Organization';
  avatarUrl: string;
}

export type GitHubEvent =
  | {
      type: 'device-code';
      userCode: string;
      verificationUri: string;
      expiresIn: number;
      interval: number;
    }
  | { type: 'auth-success'; user: GitHubUser }
  | { type: 'auth-error'; error: string; message: string }
  | { type: 'accounts-changed'; reason: 'startup-reconciliation' | 'account-updated' };
