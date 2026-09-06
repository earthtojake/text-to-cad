import { Badge, Select } from '@emdash/ui/react/primitives';
import { Github, Plus } from 'lucide-react';
import type { GitHubAccountSummary, GitHubCredentialSource } from '@core/primitives/github/api';

export const GITHUB_SOURCE_LABELS: Record<GitHubCredentialSource, string> = {
  cli: 'GitHub CLI',
  emdash_oauth: 'OAuth',
  device_flow: 'Device flow',
  secure_storage: 'Saved token',
};

/**
 * Select option encodings for the zero-account picker state (spec:
 * github-git-settings §5): with no accounts connected the dropdown offers
 * only "Inferred (none)" plus a Connect entry — never a dead list or an
 * explicit-none sentinel. The values are UI-only encodings the surrounding
 * select intercepts; they are never stored.
 */
export const GITHUB_INFERRED_NONE_OPTION = '__inferred_no_github_account__';
export const GITHUB_CONNECT_ACCOUNT_OPTION = '__connect_github_account__';

export function GitHubZeroAccountSelectItems() {
  return (
    <>
      <Select.Item value={GITHUB_INFERRED_NONE_OPTION} className="py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Github className="h-4 w-4 shrink-0 text-foreground-muted" />
          <span className="relative -top-px min-w-0 truncate">Inferred (none)</span>
          <span className="relative -top-px shrink-0 text-xs text-foreground-muted">
            No account connected
          </span>
        </div>
      </Select.Item>
      <Select.Item value={GITHUB_CONNECT_ACCOUNT_OPTION} className="py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Plus className="h-4 w-4 shrink-0 text-foreground-muted" />
          <span className="relative -top-px shrink-0">Connect GitHub account…</span>
        </div>
      </Select.Item>
    </>
  );
}

export function GitHubAccountSelectItem({ account }: { account: GitHubAccountSummary }) {
  return (
    <Select.Item value={account.accountId} className="py-2">
      <GitHubAccountSelectLabel account={account} />
    </Select.Item>
  );
}

export function GitHubAccountSelectLabel({ account }: { account: GitHubAccountSummary }) {
  return (
    <div className="flex min-w-0 flex-1 items-center gap-2 text-left">
      {account.avatarUrl ? (
        <img
          src={account.avatarUrl}
          alt={account.login}
          className="h-4 w-4 shrink-0 rounded-full"
        />
      ) : (
        <Github className="h-4 w-4 shrink-0 text-foreground-muted" />
      )}
      <span className="min-w-0 truncate" title={`@${account.login}`}>
        @{account.login}
      </span>
      <span className="shrink-0 text-xs text-foreground-muted">{account.host}</span>
      {account.isDefault ? <GitHubDefaultAccountBadge /> : null}
    </div>
  );
}

export function GitHubAccountSelectTrigger({ account }: { account: GitHubAccountSummary }) {
  return (
    <span className="flex min-w-0 flex-1 items-center gap-2 text-left">
      {account.avatarUrl ? (
        <img src={account.avatarUrl} alt={account.login} className="size-4 shrink-0 rounded-full" />
      ) : (
        <Github className="size-4 shrink-0 text-foreground-muted" />
      )}
      <span className="min-w-0 truncate">{account.login}</span>
    </span>
  );
}

export function GitHubAccountSelectListItem({ account }: { account: GitHubAccountSummary }) {
  return (
    <div className="grid grid-cols-[auto_1fr] items-center gap-x-2 gap-y-0.5">
      {account.avatarUrl ? (
        <img
          src={account.avatarUrl}
          alt={account.login}
          className="row-span-2 size-8 shrink-0 self-center rounded-full"
        />
      ) : (
        <Github className="row-span-2 size-8 shrink-0 self-center text-foreground-muted" />
      )}
      <div className="flex min-w-0 items-center gap-2">
        <span className="min-w-0 truncate font-medium">{account.login}</span>
        <GitHubCredentialSourceBadge source={account.credentialSource} />
      </div>
      <span className="text-xs text-foreground-muted">{account.host}</span>
    </div>
  );
}

export function GitHubDefaultAccountBadge() {
  return <Badge>Default</Badge>;
}

export function GitHubCredentialSourceBadge({ source }: { source: GitHubCredentialSource }) {
  return <Badge variant="outline">{GITHUB_SOURCE_LABELS[source]}</Badge>;
}
