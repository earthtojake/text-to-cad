import { Button, Checkbox, Popover, Separator } from '@emdash/ui/react/primitives';
import { Github } from 'lucide-react';
import { useState } from 'react';
import { GitHubAccountSelectLabel } from '@core/features/projects/contributions/browser/github-account-select';
import { provenanceSourceText } from '@core/features/projects/contributions/browser/settings-provenance-labels';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import type { Provenance, Resolved } from '@core/primitives/project-settings/api';
import { cn } from '@core/primitives/styling/browser/cn';
import { identityStripView } from './identity-strip-state';

/**
 * The identity strip (spec: github-git-settings §9): a slim ambient row in
 * account-relevant modals showing the acting GitHub account with provenance, a
 * popover to change the account for this action, and the fail-closed states
 * inline. The surrounding modal already names the action. The modal owns the
 * override and the blocking of its primary action (via
 * `identityStripBlocksAction`); persistence semantics are declared through
 * `persistence`.
 */
export type GitHubIdentityStripProps = {
  /** The resolver's effective account (synthetic for project-less modals). */
  resolved: Resolved<GitHubAccountSummary | null>;
  accounts: GitHubAccountSummary[];
  /** Per-action override chosen in the popover; owned by the modal. */
  override: GitHubAccountSummary | null;
  /**
   * What selecting an account in the popover does beyond the current action:
   * `per-action` offers a "Remember for this project" checkbox, `project`
   * persists every selection to the project setting (actions whose execution
   * resolves identity from the stored setting), `action-only` has no
   * persistence surface (no project yet).
   */
  persistence: 'per-action' | 'project' | 'action-only';
  /** Whether the modal's primary action genuinely requires an account. */
  accountRequired: boolean;
  onSelect: (account: GitHubAccountSummary, options: { remember: boolean }) => void;
  /** Launches the GitHub connect flow from the zero-account empty state. */
  onConnect: () => void;
};

function provenanceDotClass(provenance: Provenance): string {
  switch (provenance.kind) {
    case 'set':
      return 'bg-foreground-info';
    case 'inferred':
      return 'bg-foreground-muted';
    case 'broken-setting':
      return 'bg-foreground-warning';
    case 'unresolvable':
      return 'bg-foreground-error';
  }
}

function provenanceExplanation(
  resolved: Resolved<GitHubAccountSummary | null>,
  override: GitHubAccountSummary | null
): string {
  if (override) return 'Chosen for this action.';
  switch (resolved.provenance.kind) {
    case 'set':
      return 'Set in project settings.';
    case 'inferred':
      return `Inferred ${provenanceSourceText(resolved.provenance) ?? ''}`.trim() + '.';
    case 'broken-setting':
    case 'unresolvable':
      return 'The configured account is no longer available.';
  }
}

export function GitHubIdentityStrip({
  resolved,
  accounts,
  override,
  persistence,
  accountRequired,
  onSelect,
  onConnect,
}: GitHubIdentityStripProps) {
  const view = identityStripView(resolved, override, accounts);

  if (view.kind === 'connect') {
    return (
      <StripFrame>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <Github className="size-3.5 shrink-0 text-foreground-muted" />
          <div className="flex min-w-0 flex-col">
            <span className="text-foreground-muted">No GitHub account</span>
            <span className="text-xs text-foreground-passive">
              {accountRequired
                ? `Connect a GitHub account to continue.`
                : 'Git operations will use your system credentials.'}
            </span>
          </div>
        </div>
        <Button
          type="button"
          variant={accountRequired ? 'primary' : 'secondary'}
          size="xs"
          onClick={onConnect}
        >
          Connect
        </Button>
      </StripFrame>
    );
  }

  if (view.kind === 'unresolvable') {
    return (
      <StripFrame error>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="font-medium text-foreground-error">{view.message}</span>
          <span className="text-xs text-foreground-muted">
            {accountRequired
              ? 'Choose a GitHub account to continue.'
              : 'Pick an account, or continue with system git credentials.'}
          </span>
        </div>
        <ChangeAccountPopover
          accounts={accounts}
          current={null}
          resolved={resolved}
          override={override}
          persistence={persistence}
          onSelect={onSelect}
          trigger={
            <Button type="button" variant="primary" size="xs">
              Pick account
            </Button>
          }
        />
      </StripFrame>
    );
  }

  const account = view.kind === 'account' ? view.account : null;

  return (
    <StripFrame>
      <div className="flex min-w-0 flex-1 items-center gap-2">
        {view.kind === 'disabled' ? (
          <span className="min-w-0 truncate text-foreground-muted">{view.message}</span>
        ) : (
          <>
            <span
              className={cn(
                'size-2 shrink-0 rounded-full',
                provenanceDotClass(
                  account && view.kind === 'account' ? view.provenance : resolved.provenance
                )
              )}
              title={provenanceExplanation(resolved, override)}
            />
            <span className="shrink-0 text-foreground-muted">Creating as</span>
            {account ? (
              <GitHubAccountSelectLabel account={account} />
            ) : (
              <span className="text-foreground-muted">—</span>
            )}
            {view.kind === 'no-match' ? (
              <span className="min-w-0 truncate text-xs text-foreground-passive">
                No connected account matches this repository.
              </span>
            ) : null}
          </>
        )}
      </div>
      <ChangeAccountPopover
        accounts={accounts}
        current={account}
        resolved={resolved}
        override={override}
        persistence={persistence}
        onSelect={onSelect}
        trigger={
          <Button type="button" variant="ghost" size="xs">
            Change
          </Button>
        }
      />
    </StripFrame>
  );
}

function StripFrame({ error, children }: { error?: boolean; children: React.ReactNode }) {
  return (
    <div
      data-testid="github-identity-strip"
      className={cn(
        'flex items-center gap-2 rounded-md border px-3 py-2 text-sm',
        error ? 'border-border-error bg-background-error/20' : 'border-border bg-background-1'
      )}
    >
      {children}
    </div>
  );
}

function ChangeAccountPopover({
  accounts,
  current,
  resolved,
  override,
  persistence,
  onSelect,
  trigger,
}: {
  accounts: GitHubAccountSummary[];
  current: GitHubAccountSummary | null;
  resolved: Resolved<GitHubAccountSummary | null>;
  override: GitHubAccountSummary | null;
  persistence: 'per-action' | 'project' | 'action-only';
  onSelect: (account: GitHubAccountSummary, options: { remember: boolean }) => void;
  trigger: React.ReactElement;
}) {
  const [open, setOpen] = useState(false);
  const [remember, setRemember] = useState(false);

  if (accounts.length === 0) return null;

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger render={trigger} />
      <Popover.Content align="end" className="flex w-72 flex-col gap-2 p-3">
        <span className="text-xs font-medium text-foreground-muted">Act as</span>
        <div className="flex flex-col gap-1">
          {accounts.map((candidate) => (
            <button
              key={candidate.accountId}
              type="button"
              onClick={() => {
                onSelect(candidate, { remember: persistence === 'project' ? true : remember });
                setOpen(false);
              }}
              className={cn(
                'flex items-center rounded-md px-2 py-1.5 text-left text-sm hover:bg-background-2',
                current?.accountId === candidate.accountId && 'bg-background-2'
              )}
            >
              <GitHubAccountSelectLabel account={candidate} />
            </button>
          ))}
        </div>
        {persistence === 'action-only' ? null : (
          <>
            <Separator />
            {persistence === 'per-action' ? (
              <label className="flex cursor-pointer items-center gap-2 text-xs text-foreground-muted">
                <Checkbox
                  checked={remember}
                  onCheckedChange={(checked) => setRemember(checked === true)}
                />
                Remember for this project
              </label>
            ) : (
              <span className="text-xs text-foreground-passive">
                Selections apply to this project.
              </span>
            )}
          </>
        )}
        <span className="text-xs text-foreground-passive">
          {provenanceExplanation(resolved, override)}
        </span>
      </Popover.Content>
    </Popover.Root>
  );
}
