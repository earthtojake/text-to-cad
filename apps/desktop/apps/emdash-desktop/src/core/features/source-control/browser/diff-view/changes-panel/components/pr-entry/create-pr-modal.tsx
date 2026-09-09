import type { GitBranchRef } from '@emdash/core/runtimes/git/api';
import {
  Alert,
  Combobox,
  Dialog,
  Field,
  Input,
  Separator,
  SplitButton,
  Textarea,
} from '@emdash/ui/react/primitives';
import { ChevronDown, GitBranch, GitPullRequest } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useMemo, useState } from 'react';
import { useGitHubAccounts } from '@core/features/github/api/browser/useGithubAccounts';
import { GitHubIdentityStrip } from '@core/features/github/contributions/browser/identity-strip';
import { persistProjectGitHubAccount } from '@core/features/github/contributions/browser/identity-strip-persist';
import {
  identityStripBlocksAction,
  identityStripView,
} from '@core/features/github/contributions/browser/identity-strip-state';
import { useEffectiveSettings } from '@core/features/projects/api/browser/effective-settings/use-effective-settings';
import { BrokenSettingNotice } from '@core/features/projects/contributions/browser/settings-provenance';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import { formatPushErrorDetail } from '@core/features/source-control/api/git-error-messages';
import { BranchDisplay } from '@core/features/source-control/contributions/browser/branch-display';
import { ProjectBranchSelector } from '@core/features/source-control/contributions/browser/project-branch-selector';
import { RemoteSelector } from '@core/features/source-control/contributions/browser/remote-selector';
import { gitCheckoutStoreToken } from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import { workspaceRegistry } from '@core/features/workspaces/api/browser/stores/workspace-registry';
import { useModalController, useOpenModal } from '@core/manifests/browser/modal-api';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { log } from '@core/primitives/logging/browser/logger';
import { defineModal } from '@core/primitives/modals/react';
import { parseRepositoryRef } from '@core/primitives/repository/api';
import { pullRequestErrorMessage } from '@core/services/pull-requests/api';
import { getPullRequestsRuntimeClient } from '@core/services/pull-requests/api/client';
import { resolveInitialBaseBranch } from './base-branch';
import { getTargetRemotes, resolveCreatePrTargetRemote } from './target-remote';

export type CreatePrModalArgs = {
  projectId: string;
  taskId: string;
  repositoryUrl: string;
  branchName: string;
  draft: boolean;
  workspaceId: string;
};

export const CreatePrModal = observer(function CreatePrModal({
  projectId,
  taskId: _taskId,
  repositoryUrl,
  branchName,
  draft,
  workspaceId,
}: CreatePrModalArgs) {
  const { complete } = useModalController('createPrModal');
  const openGithubConnectModal = useOpenModal('githubConnectModal');
  const [title, setTitle] = useState(branchName);
  const [description, setDescription] = useState('');
  const [selectedBaseOverride, setSelectedBaseOverride] = useState<GitBranchRef | undefined>();
  const [selectedTargetRemoteName, setSelectedTargetRemoteName] = useState<string | undefined>();
  const [isCreating, setIsCreating] = useState(false);
  const [createActionId, setCreateActionId] = useState('push-and-create');
  const [error, setError] = useState<string | null>(null);
  const [accountOverride, setAccountOverride] = useState<GitHubAccountSummary | null>(null);
  const repo = getGitRepositoryStore(projectId);
  const checkout = workspaceRegistry.get(workspaceId)?.get(gitCheckoutStoreToken);
  // Identity strip inputs (spec §9): the resolver's effective account plus the
  // per-action override. Create-PR is fail-closed (spec §5/§7): while the
  // inputs load or when no account resolves, the primary action stays blocked.
  const effective = useEffectiveSettings(projectId);
  const { data: accounts } = useGitHubAccounts();
  const resolvedAccount = effective?.githubAccount ?? null;
  const identityBlocked =
    !resolvedAccount ||
    !accounts ||
    identityStripBlocksAction(identityStripView(resolvedAccount, accountOverride, accounts), true);
  // The PR execution path resolves *as whom* node-side from the stored
  // per-project setting, so a popover selection persists immediately (the
  // popover says so) instead of riding a per-action parameter.
  const handleSelectAccount = (account: GitHubAccountSummary) => {
    setAccountOverride(account);
    void persistProjectGitHubAccount(projectId, account.accountId);
  };
  const defaultBranch = repo?.defaultBranchRef;
  const needsPush = !checkout?.isPublished || checkout.aheadCount > 0;
  const baseRemoteResolution = repo?.effectiveGitSettings.baseRemote ?? null;
  const projectRemoteName = repo?.baseRemote?.name ?? null;
  const fallbackRepository = useMemo(() => parseRepositoryRef(repositoryUrl), [repositoryUrl]);
  const targetRemotes = useMemo(
    () =>
      fallbackRepository
        ? getTargetRemotes(repo?.remotes ?? [], { host: fallbackRepository.host })
        : [],
    [fallbackRepository, repo?.remotes]
  );
  const targetRemote = resolveCreatePrTargetRemote({
    options: targetRemotes,
    projectRemoteName,
    selectedRemoteName: selectedTargetRemoteName,
    fallbackRepositoryUrl: repositoryUrl,
  });
  const targetRepositoryUrl =
    targetRemote?.repository.repositoryUrl ?? fallbackRepository?.repositoryUrl ?? null;

  const hasGitHubRemote = Boolean(targetRepositoryUrl);
  const selectedBase =
    selectedBaseOverride ??
    resolveInitialBaseBranch(
      repo?.branchRefs.filter((branch) => branch.type === 'remote') ?? [],
      undefined,
      defaultBranch,
      targetRemote?.remote.name ?? projectRemoteName
    );

  const handleTargetRemoteChange = (remoteName: string) => {
    setSelectedTargetRemoteName(remoteName);
    setSelectedBaseOverride(undefined);
  };

  const doCreate = async (push: boolean) => {
    if (!selectedBase?.branch) {
      setError('Select a base branch before creating the pull request.');
      return;
    }
    if (!title.trim() || !targetRepositoryUrl) return;
    setError(null);
    setIsCreating(true);
    try {
      if (push) {
        const workspace = workspaceRegistry.get(workspaceId);
        if (!workspace) throw new Error('Workspace is unavailable');
        const pushResult = await workspace.get(gitCheckoutStoreToken).push();
        if (!pushResult.success) {
          log.error('Failed to push branch:', pushResult.error);
          setError(formatPushErrorDetail(pushResult.error));
          return;
        }
      }

      const baseRepository = parseRepositoryRef(targetRepositoryUrl);
      const headRepository = repo?.pushRemote?.url ? parseRepositoryRef(repo.pushRemote.url) : null;
      const head =
        baseRepository &&
        headRepository &&
        headRepository.repositoryUrl !== baseRepository.repositoryUrl
          ? `${headRepository.owner}:${branchName}`
          : branchName;

      const client = await getPullRequestsRuntimeClient();
      const result = await client.createPullRequest({
        repositoryUrl: targetRepositoryUrl,
        headRepositoryUrl: headRepository?.repositoryUrl,
        head,
        base: selectedBase.branch,
        title: title.trim(),
        body: description.trim() || undefined,
        draft,
      });

      if (result.success) {
        await client.syncSingle({
          repositoryUrl: targetRepositoryUrl,
          number: result.data.number,
        });
        complete();
      } else {
        setError(pullRequestErrorMessage(result.error));
      }
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <div className="flex max-h-[70vh] flex-col overflow-hidden">
      <Dialog.Header>
        <Dialog.Title>{draft ? 'Create Draft PR' : 'Create Pull Request'}</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="space-y-4">
        {!hasGitHubRemote && (
          <p className="text-sm text-foreground-muted">
            No GitHub remote detected. Configure a GitHub remote to create pull requests.
          </p>
        )}
        {baseRemoteResolution?.provenance.kind === 'broken-setting' ? (
          <BrokenSettingNotice
            staleValue={baseRemoteResolution.provenance.staleValue}
            effectiveValue={baseRemoteResolution.value}
          />
        ) : null}
        <div className="flex flex-col items-center gap-2">
          <BranchDisplay
            label="Head Branch"
            branchName={branchName}
            className="rounded-md border border-border"
          />
          {targetRemotes.length > 1 && targetRemote ? (
            <RemoteSelector
              remotes={targetRemotes.map(({ remote }) => remote)}
              value={targetRemote.remote.name}
              onValueChange={handleTargetRemoteChange}
              className="min-h-[58px] w-full"
              renderTrigger={(selected) => (
                <div className="flex flex-col gap-0.5 text-left text-sm">
                  <span className="text-xs text-foreground-passive">Target</span>
                  <span className="flex items-center gap-1">
                    <GitPullRequest
                      absoluteStrokeWidth
                      strokeWidth={2}
                      className="size-3.5 shrink-0 text-foreground-muted"
                    />
                    <span className="min-w-0 truncate">
                      {selected?.label ?? targetRemote.remote.name}
                    </span>
                  </span>
                </div>
              )}
            />
          ) : null}
          <ProjectBranchSelector
            projectId={projectId}
            value={selectedBase}
            onValueChange={setSelectedBaseOverride}
            remoteOnly
            remoteName={targetRemote?.remote.name}
            branchLabelRemote="short"
            trigger={
              <Combobox.Trigger className="flex w-full items-center justify-between gap-2 rounded-md border border-border p-2 text-left outline-none">
                <div className="flex flex-col gap-0.5 text-left text-sm">
                  <span className="text-xs text-foreground-passive">Base Branch</span>
                  <span className="flex items-center gap-1">
                    <GitBranch
                      absoluteStrokeWidth
                      strokeWidth={2}
                      className="size-3.5 shrink-0 text-foreground-muted"
                    />
                    <Combobox.Value placeholder="Select a base branch" />
                  </span>
                </div>
                <ChevronDown className="size-4 shrink-0 text-foreground-muted" />
              </Combobox.Trigger>
            }
          />
        </div>
        <Separator />
        <Field.Group>
          <Field.Root>
            <Field.Label>Title</Field.Label>
            <Input
              placeholder="PR title"
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={!hasGitHubRemote}
            />
          </Field.Root>
          <Field.Root>
            <Field.Label>Description</Field.Label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={1}
              disabled={!hasGitHubRemote}
            />
          </Field.Root>
        </Field.Group>
        {resolvedAccount && accounts ? (
          <GitHubIdentityStrip
            resolved={resolvedAccount}
            accounts={accounts}
            override={accountOverride}
            persistence="project"
            accountRequired
            onSelect={handleSelectAccount}
            onConnect={() => void openGithubConnectModal({})}
          />
        ) : null}
        {error && (
          <Alert.Root status="destructive">
            <Alert.Title>Failed to create pull request</Alert.Title>
            <Alert.Description>{error}</Alert.Description>
          </Alert.Root>
        )}
      </Dialog.Body>
      <Dialog.Footer>
        {needsPush ? (
          <SplitButton
            size="sm"
            loading={isCreating}
            loadingLabel="Creating..."
            disabled={!hasGitHubRemote || !selectedBase?.branch || !title.trim() || identityBlocked}
            options={[
              {
                id: 'push-and-create',
                label: draft ? 'Push & Create Draft' : 'Push & Create PR',
              },
              {
                id: 'create-only',
                label: draft ? 'Create Draft' : 'Create PR',
                description: 'Skip push and open a PR from the current remote state',
              },
            ]}
            selectedId={createActionId}
            onSelectedChange={setCreateActionId}
            commitOnSelect={false}
            onAction={(id) => void doCreate(id === 'push-and-create')}
          />
        ) : (
          <ConfirmButton
            variant="primary"
            size="sm"
            onClick={() => void doCreate(false)}
            disabled={
              !hasGitHubRemote ||
              !selectedBase?.branch ||
              !title.trim() ||
              isCreating ||
              identityBlocked
            }
          >
            {isCreating ? 'Creating...' : draft ? 'Create Draft' : 'Create PR'}
          </ConfirmButton>
        )}
      </Dialog.Footer>
    </div>
  );
});

export const createPrModal = defineModal<void>()({
  id: 'createPrModal',
  component: CreatePrModal,
  size: 'md',
});
