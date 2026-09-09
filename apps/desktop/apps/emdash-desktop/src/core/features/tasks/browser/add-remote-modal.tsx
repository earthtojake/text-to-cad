import { ComboboxPopover } from '@emdash/ui/react/components';
import {
  Dialog,
  Field,
  Input,
  Label,
  ModalLayout,
  RadioGroup,
  ToggleGroup,
} from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import { getGithubClient } from '@core/features/github/api/browser/client';
import { useGitHubAccounts } from '@core/features/github/api/browser/useGithubAccounts';
import { useGitHubRepositoryOwnerSelect } from '@core/features/github/api/browser/useGithubRepositoryOwners';
import { GitHubIdentityStrip } from '@core/features/github/contributions/browser/identity-strip';
import { persistProjectGitHubAccount } from '@core/features/github/contributions/browser/identity-strip-persist';
import { useEffectiveSettings } from '@core/features/projects/api/browser/effective-settings/use-effective-settings';
import { BrokenSettingNotice } from '@core/features/projects/contributions/browser/settings-provenance';
import {
  getGitCheckoutStore,
  getGitRepositoryStore,
} from '@core/features/source-control/api/browser/stores/source-control-selectors';
import { useModalController, useOpenModal } from '@core/manifests/browser/modal-api';
import { DEFAULT_REMOTE_NAME } from '@core/primitives/git/api';
import type { GitHubAccountSummary } from '@core/primitives/github/api';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';

export type AddRemoteModalArgs = {
  projectId: string;
  projectName: string;
  workspaceId: string;
};

type Tab = 'create' | 'link';

function toErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'string' && error.length > 0) return error;
  if (error instanceof Error && error.message.length > 0) return error.message;
  return fallback;
}

export const AddRemoteModal = observer(function AddRemoteModal({
  projectId,
  projectName,
  workspaceId,
}: AddRemoteModalArgs) {
  const { complete } = useModalController('addRemoteModal');
  const openGithubConnectModal = useOpenModal('githubConnectModal');
  const [tab, setTab] = useState<Tab>('create');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [repositoryName, setRepositoryName] = useState(projectName);
  const [visibility, setVisibility] = useState<'public' | 'private'>('private');
  const [url, setUrl] = useState('');
  const [accountOverride, setAccountOverride] = useState<GitHubAccountSummary | null>(null);

  // The account acting for this modal (spec §9): the identity strip's
  // per-action override, else the blessed resolver's effective account. The
  // old hard refusal ("select a GitHub account in project settings first") is
  // gone — the strip carries both the identity and the fix-it path inline.
  const effective = useEffectiveSettings(projectId);
  const { data: accounts } = useGitHubAccounts();
  const resolvedAccount = effective?.githubAccount ?? null;
  const actingAccount = accountOverride ?? resolvedAccount?.value ?? null;
  const githubAccountId = actingAccount?.accountId ?? null;

  const handleSelectAccount = (
    account: GitHubAccountSummary,
    { remember }: { remember: boolean }
  ) => {
    setAccountOverride(account);
    if (remember) void persistProjectGitHubAccount(projectId, account.accountId);
  };

  const {
    owners,
    owner,
    isLoading: ownersLoading,
    errorMessage: ownersErrorMessage,
    handleOwnerChange,
  } = useGitHubRepositoryOwnerSelect(githubAccountId);
  const repositoryStore = getGitRepositoryStore(projectId);
  const checkoutStore = getGitCheckoutStore(workspaceId);
  const pushRemoteResolution = repositoryStore?.effectiveGitSettings.pushRemote ?? null;
  // The effective push remote when one resolves; otherwise this modal is
  // creating the repository's first remote, and DEFAULT_REMOTE_NAME is the
  // conventional name for a brand-new remote (a naming default, not
  // resolution).
  const selectedRemote = repositoryStore?.pushRemote?.name ?? DEFAULT_REMOTE_NAME;
  // Creating a GitHub repository genuinely requires an account (fail closed);
  // linking an existing remote proceeds on system credentials (spec §5).
  const canSubmitCreateRepository =
    githubAccountId !== null &&
    !ownersLoading &&
    !ownersErrorMessage &&
    repositoryName.trim().length > 0 &&
    !!owner;
  const isValid = tab === 'create' ? canSubmitCreateRepository : url.trim().length > 0;

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setError(null);

    try {
      if (tab === 'create') {
        if (!githubAccountId) return;
        if (!owner) {
          setError(ownersErrorMessage ?? 'No repository owner available');
          return;
        }

        const result = await (
          await getGithubClient()
        ).createRepository({
          name: repositoryName.trim(),
          owner: owner.value,
          isPrivate: visibility === 'private',
          accountId: githubAccountId,
        });

        if (!result.success) {
          setError(result.error ?? 'Failed to create repository');
          return;
        }

        if (!result.repoUrl) {
          setError('Created repository did not include a remote URL');
          return;
        }

        if (!repositoryStore) throw new Error('Git repository is unavailable');
        const addRemoteResult = await repositoryStore.addRemote(selectedRemote, result.repoUrl);

        if (!addRemoteResult.success) {
          setError(toErrorMessage(addRemoteResult.error, 'Failed to add remote'));
          return;
        }
      } else {
        if (!repositoryStore) throw new Error('Git repository is unavailable');
        const addRemoteResult = await repositoryStore.addRemote(selectedRemote, url.trim());

        if (!addRemoteResult.success) {
          setError(toErrorMessage(addRemoteResult.error, 'Failed to add remote'));
          return;
        }
      }

      if (!repositoryStore) throw new Error('Git repository is unavailable');
      const fetchResult = await repositoryStore.fetchRemote();
      if (!fetchResult.success) {
        setError(toErrorMessage(fetchResult.error, 'Failed to fetch remote'));
        return;
      }

      if (!checkoutStore) throw new Error('Git checkout is unavailable');
      const publishResult = await checkoutStore.publishCurrentBranch();
      if (!publishResult.success) {
        if (publishResult.error.type === 'rejected') {
          repositoryStore?.refreshLocal();
          repositoryStore?.refreshRemote();
          setError(
            'Remote already has commits. Linking succeeded, but integrating histories must be resolved manually.'
          );
          return;
        }
        setError(toErrorMessage(publishResult.error, 'Failed to publish branch'));
        return;
      }

      repositoryStore?.refreshLocal();
      repositoryStore?.refreshRemote();
      complete();
    } catch (e) {
      setError(toErrorMessage(e, 'An error occurred'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <ModalLayout
      header={
        <Dialog.Header>
          <Dialog.Title>Add Remote</Dialog.Title>
        </Dialog.Header>
      }
      footer={
        <Dialog.Footer>
          <ConfirmButton
            variant="primary"
            onClick={() => void handleSubmit()}
            disabled={!isValid || isSubmitting}
          >
            {isSubmitting ? 'Adding...' : tab === 'create' ? 'Create & Publish' : 'Link & Publish'}
          </ConfirmButton>
        </Dialog.Footer>
      }
    >
      <Dialog.Body className="gap-4">
        <ToggleGroup.Root
          className="flex w-full"
          value={[tab]}
          onValueChange={([v]) => {
            if (v) setTab(v as Tab);
          }}
        >
          <ToggleGroup.Item className="flex-1" value="create">
            Create Repository
          </ToggleGroup.Item>
          <ToggleGroup.Item className="flex-1" value="link">
            Link Existing
          </ToggleGroup.Item>
        </ToggleGroup.Root>

        {tab === 'create' && (
          <Field.Group>
            <Field.Root>
              <Field.Label>Repository Name</Field.Label>
              <Input
                autoFocus
                value={repositoryName}
                onChange={(e) => setRepositoryName(e.target.value)}
              />
            </Field.Root>
            <Field.Root>
              <Field.Label>Owner</Field.Label>
              <ComboboxPopover
                items={owners}
                value={owner?.value ?? null}
                onValueChange={(next) => {
                  const match = owners.find((o) => o.value === next);
                  if (match) handleOwnerChange(match);
                }}
                itemToKey={(o) => o.value}
                itemToLabel={(o) => o.label}
                renderTrigger={(selected) => selected?.label ?? 'Select owner'}
                renderItem={(o) => o.label}
                appearance="input"
                className="w-full"
              />
              {ownersErrorMessage && (
                <p className="text-xs text-foreground-destructive">{ownersErrorMessage}</p>
              )}
            </Field.Root>
            <Field.Root>
              <Field.Label>Visibility</Field.Label>
              <RadioGroup.Root
                value={visibility}
                onValueChange={(v) => setVisibility(v as 'public' | 'private')}
              >
                <Label className="flex cursor-pointer items-center gap-3 font-normal">
                  <RadioGroup.Item value="private" />
                  Private
                </Label>
                <Label className="flex cursor-pointer items-center gap-3 font-normal">
                  <RadioGroup.Item value="public" />
                  Public
                </Label>
              </RadioGroup.Root>
            </Field.Root>
          </Field.Group>
        )}

        {tab === 'link' && (
          <Field.Group>
            <Field.Root>
              <Field.Label>Remote URL</Field.Label>
              <Input
                autoFocus
                placeholder="https://git.example.com/owner/repo.git"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
            </Field.Root>
          </Field.Group>
        )}

        {pushRemoteResolution?.provenance.kind === 'broken-setting' ? (
          <BrokenSettingNotice
            staleValue={pushRemoteResolution.provenance.staleValue}
            effectiveValue={pushRemoteResolution.value}
          />
        ) : null}

        {resolvedAccount && accounts ? (
          <GitHubIdentityStrip
            resolved={resolvedAccount}
            accounts={accounts}
            override={accountOverride}
            persistence="per-action"
            accountRequired={tab === 'create'}
            onSelect={handleSelectAccount}
            onConnect={() => void openGithubConnectModal({})}
          />
        ) : null}

        {error && <p className="text-sm text-foreground-destructive">{error}</p>}
      </Dialog.Body>
    </ModalLayout>
  );
});

export const addRemoteModal = defineModal<void>()({
  id: 'addRemoteModal',
  component: AddRemoteModal,
});
