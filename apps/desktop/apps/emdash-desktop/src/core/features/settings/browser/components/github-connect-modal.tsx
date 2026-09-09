import { Button, Dialog, useToast } from '@emdash/ui/react/primitives';
import {
  AlertCircle,
  ArrowRight,
  KeyRound,
  Loader2,
  type LucideIcon,
  Terminal,
} from 'lucide-react';
import { useState } from 'react';
import {
  useGitHubDeviceFlowAuth,
  useImportGitHubCliAccounts,
} from '@core/features/github/api/browser/useGithubAccounts';
import { useModalController, useOpenModal } from '@core/manifests/browser/modal-api';
import { defineModal } from '@core/primitives/modals/react';
import { cn } from '@core/primitives/styling/browser/cn';

type MethodError = {
  method: 'cli' | 'device_flow';
  message: string;
} | null;

export function GithubConnectModal() {
  const modal = useModalController('githubConnectModal');
  const { toast } = useToast();
  const deviceFlowMutation = useGitHubDeviceFlowAuth();
  const importCliAccountsMutation = useImportGitHubCliAccounts();
  const openDeviceFlow = useOpenModal('githubDeviceFlowModal');
  const [cliLoading, setCliLoading] = useState(false);
  const [error, setError] = useState<MethodError>(null);

  const deviceFlowLoading = deviceFlowMutation.isPending;
  const anyLoading = cliLoading || deviceFlowLoading;

  const refreshCliAuth = async () => {
    setError(null);
    setCliLoading(true);
    try {
      const result = await importCliAccountsMutation.mutateAsync();
      if (!result.success) {
        setError({
          method: 'cli',
          message: result.error,
        });
        return;
      }

      if (result.importedAccountIds.length === 0) {
        setError({
          method: 'cli',
          message: 'No GitHub CLI session found. Run gh auth login first.',
        });
        return;
      }

      toast('GitHub CLI accounts imported', {
        description:
          result.importedAccountIds.length === 1
            ? '1 account is available in Hardcore.'
            : `${result.importedAccountIds.length} accounts are available in Hardcore.`,
      });
      modal.complete();
    } finally {
      setCliLoading(false);
    }
  };

  const connectDeviceFlow = () => {
    setError(null);
    // Completing this modal when the device flow succeeds resumes whatever the
    // connect flow interrupted (spec: github-git-settings §5): a modal that
    // launched connect from its identity strip stays open underneath the stack
    // and becomes topmost again. A dismissed device flow keeps this modal open
    // so the user can retry another method.
    const deviceFlowOutcome = openDeviceFlow({});
    void deviceFlowMutation.mutateAsync();
    void deviceFlowOutcome.then((outcome) => {
      if (outcome.success) modal.complete();
    });
  };

  return (
    <>
      <Dialog.Header>
        <Dialog.Title>Connect GitHub</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="gap-3">
        <ConnectMethodCard
          icon={Terminal}
          title="Import from GitHub CLI"
          description="Use accounts already authenticated with GitHub CLI"
          label="Import from GitHub CLI"
          loadingLabel="Checking GitHub CLI accounts"
          loading={cliLoading}
          disabled={anyLoading}
          onClick={() => void refreshCliAuth()}
          error={error?.method === 'cli' ? error.message : undefined}
        />

        <ConnectMethodCard
          icon={KeyRound}
          title="Use device flow"
          description="Connect GitHub on this device with a one-time code"
          label="Use device flow"
          loadingLabel="Opening device flow"
          loading={deviceFlowLoading}
          disabled={anyLoading}
          onClick={connectDeviceFlow}
          error={error?.method === 'device_flow' ? error.message : undefined}
        />
      </Dialog.Body>
      <Dialog.Footer>
        <Button variant="secondary" onClick={modal.dismiss} disabled={anyLoading}>
          Cancel
        </Button>
      </Dialog.Footer>
    </>
  );
}

export const githubConnectModal = defineModal<void>()({
  id: 'githubConnectModal',
  component: GithubConnectModal,
  size: 'md',
});

function ConnectMethodCard({
  icon: Icon,
  title,
  description,
  label,
  loadingLabel,
  loading,
  disabled,
  onClick,
  error,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  label: string;
  loadingLabel: string;
  loading: boolean;
  disabled: boolean;
  onClick: () => void;
  error?: string;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        aria-label={loading ? loadingLabel : label}
        className={cn(
          'group flex w-full items-center gap-3 p-3 text-left transition-colors',
          'hover:bg-background-2',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
          'disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:bg-transparent'
        )}
      >
        <Icon className="h-4 w-4 shrink-0 text-foreground-muted" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium text-foreground">{title}</h3>
          <p className="mt-0.5 text-xs text-foreground-muted">{description}</p>
        </div>
        {loading ? (
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-foreground-muted" />
        ) : (
          <ArrowRight className="h-4 w-4 shrink-0 text-foreground-muted transition-transform group-hover:translate-x-0.5" />
        )}
      </button>
      {error && <InlineError message={error} className="mx-3 mt-2 mb-3" />}
    </div>
  );
}

function InlineError({ message, className }: { message: string; className?: string }) {
  return (
    <div
      className={cn(
        'bg-background-destructive/10 text-foreground-destructive flex items-start gap-1.5 rounded-md px-2.5 py-2 text-xs',
        className
      )}
    >
      <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
