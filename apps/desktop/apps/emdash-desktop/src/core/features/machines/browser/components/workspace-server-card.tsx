import { UpdateCard, type UpdateStatus } from '@emdash/ui/react/components';
import { SettingsRow } from '@emdash/ui/react/patterns';
import { Button, SplitButton } from '@emdash/ui/react/primitives';
import { DownloadIcon, LoaderCircleIcon, PlayIcon } from 'lucide-react';
import type { HostServerState } from '@core/services/hosts/api';
import { WorkspaceServerBadge } from './workspace-server-badge';

type WorkspaceServerActions = {
  install(): Promise<void>;
  start(): Promise<void>;
  stop(): Promise<void>;
  restart(): Promise<void>;
  update(): Promise<void>;
  refresh(): Promise<void>;
};

export function WorkspaceRuntimeRow({
  connected,
  loading,
  state,
  actions,
}: {
  connected: boolean;
  loading: boolean;
  state: HostServerState | undefined;
  actions: WorkspaceServerActions;
}) {
  return (
    <div className="flex flex-col gap-3">
      <SettingsRow
        label={
          <span className="flex items-center gap-2">
            Workspace Runtime
            {connected && !loading && state && (
              <WorkspaceServerBadge status={state.status} error={state.error} />
            )}
          </span>
        }
        description={
          <WorkspaceRuntimeDetails connected={connected} loading={loading} state={state} />
        }
        control={
          connected && !loading && state ? (
            <WorkspaceServerAction state={state} actions={actions} />
          ) : null
        }
      />
      {state?.version !== undefined && (
        <UpdateCard
          appName="workspace server"
          currentVersion={state.version}
          status={workspaceServerUpdateStatus(state, actions)}
          onCheckForUpdates={actions.refresh}
          error={state.error}
        />
      )}
    </div>
  );
}

function workspaceServerUpdateStatus(
  state: HostServerState,
  actions: WorkspaceServerActions
): UpdateStatus {
  if (
    state.updateAvailable === true &&
    state.latestVersion !== undefined &&
    state.error?.code !== 'protocol-upgrade-client'
  ) {
    return {
      type: 'update-available',
      version: state.latestVersion,
      onUpdate: actions.update,
    };
  }

  return { type: 'up-to-date' };
}

function WorkspaceRuntimeDetails({
  connected,
  loading,
  state,
}: {
  connected: boolean;
  loading: boolean;
  state: HostServerState | undefined;
}) {
  if (!connected) return 'Connect to this machine to inspect its workspace runtime.';

  if (loading || !state) {
    return (
      <span className="flex items-center gap-2">
        <LoaderCircleIcon className="size-3.5 animate-spin" />
        Checking workspace runtime…
      </span>
    );
  }

  const startedAt =
    state.startedAt !== undefined && state.status === 'healthy'
      ? new Date(state.startedAt).toLocaleString()
      : undefined;

  return (
    <span className="flex flex-col gap-1">
      {(state.version || startedAt) && (
        <span className="flex flex-wrap items-center gap-2">
          {state.version && <span className="tabular-nums">Runtime v{state.version}</span>}
          {state.version && startedAt && <span aria-hidden>·</span>}
          {startedAt && <span>Started {startedAt}</span>}
          {state.detail && <span>{state.detail}</span>}
        </span>
      )}
      {state.error && <span className="text-foreground-destructive">{state.error.message}</span>}
    </span>
  );
}

function WorkspaceServerAction({
  state,
  actions,
}: {
  state: HostServerState;
  actions: WorkspaceServerActions;
}) {
  const transitioning = state.status === 'booting' || state.status === 'shutting-down';

  if (state.status === 'not-installed') {
    return (
      <Button
        type="button"
        variant="primary"
        size="xs"
        disabled={transitioning}
        onClick={() => void actions.install()}
      >
        <DownloadIcon />
        Install
      </Button>
    );
  }

  if (state.status === 'stopped') {
    return (
      <Button
        type="button"
        variant="primary"
        size="xs"
        disabled={transitioning}
        onClick={() => void actions.start()}
      >
        <PlayIcon />
        Start
      </Button>
    );
  }

  if (
    state.status === 'healthy' ||
    state.status === 'failed' ||
    state.status === 'booting' ||
    state.status === 'shutting-down'
  ) {
    return (
      <SplitButton
        options={[
          {
            id: 'restart',
            label: 'Restart',
          },
          {
            id: 'shutdown',
            label: 'Shutdown',
          },
        ]}
        selectedId="restart"
        onAction={(id) => {
          if (id === 'shutdown') {
            void actions.stop();
            return;
          }
          void actions.restart();
        }}
        variant="secondary"
        size="xs"
        disabled={transitioning}
      />
    );
  }

  return null;
}
