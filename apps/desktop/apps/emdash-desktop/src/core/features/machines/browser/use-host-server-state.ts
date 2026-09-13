import { toast } from '@emdash/ui/react/primitives';
import { remote, type RemoteModel } from '@emdash/wire/state';
import { useCallback, useEffect } from 'react';
import { useRemoteModelState } from '@core/primitives/wire/browser/use-remote-model-state';
import { hostsContract, type HostServerState } from '@core/services/hosts/api';
import { getHostsClient } from '@core/services/hosts/api/client';

type ServerAction =
  | 'installServer'
  | 'startServer'
  | 'stopServer'
  | 'restartServer'
  | 'updateServer';

let serverStatesRemotePromise: Promise<RemoteModel<typeof hostsContract.serverStates>> | undefined;

export function useHostServerState({
  machineId,
  enabled,
  connected,
}: {
  machineId: string | undefined;
  enabled: boolean;
  connected: boolean;
}): {
  state: HostServerState | undefined;
  loading: boolean;
  install(): Promise<void>;
  start(): Promise<void>;
  stop(): Promise<void>;
  restart(): Promise<void>;
  update(): Promise<void>;
  refresh(): Promise<void>;
} {
  const runtimeState = useRemoteModelState(
    hostsContract.serverStates,
    getServerStatesRemote,
    undefined,
    'runtime',
    {
      enabled: enabled && machineId !== undefined,
      initialValue: {},
    }
  );

  let state: HostServerState | undefined;
  if (connected && machineId) {
    state = runtimeState.value?.[machineId];
  }

  useEffect(() => {
    if (!enabled || !connected || !machineId || !runtimeState.ready) return;
    if (hasRecentLatestVersion(state)) return;
    let cancelled = false;
    void getHostsClient()
      .then((client) => client.refreshServerState({ connectionId: machineId }))
      .catch(() => {
        if (cancelled) return;
      });
    return () => {
      cancelled = true;
    };
  }, [connected, enabled, machineId, runtimeState.ready, state]);

  const runAction = useCallback(
    async (action: ServerAction, label: string) => {
      if (!machineId) return;
      try {
        const client = await getHostsClient();
        await client[action]({ connectionId: machineId });
      } catch (error) {
        toast.error(`Failed to ${label} workspace server`, {
          description: error instanceof Error ? error.message : String(error),
        });
      }
    },
    [machineId]
  );

  const refresh = useCallback(async () => {
    if (!machineId) return;
    try {
      const client = await getHostsClient();
      await client.refreshServerState({ connectionId: machineId, force: true });
    } catch (error) {
      toast.error('Failed to check workspace server updates', {
        description: error instanceof Error ? error.message : String(error),
      });
    }
  }, [machineId]);

  return {
    state,
    loading: enabled && connected && (!runtimeState.ready || !state),
    install: () => runAction('installServer', 'install'),
    start: () => runAction('startServer', 'start'),
    stop: () => runAction('stopServer', 'shut down'),
    restart: () => runAction('restartServer', 'restart'),
    update: () => runAction('updateServer', 'update'),
    refresh,
  };
}

function hasRecentLatestVersion(state: HostServerState | undefined): boolean {
  return state?.latestVersion !== undefined;
}

function getServerStatesRemote(): Promise<RemoteModel<typeof hostsContract.serverStates>> {
  serverStatesRemotePromise ??= getHostsClient().then((client) =>
    remote(hostsContract.serverStates, client.serverStates, {
      lingerMs: 15_000,
    })
  );
  return serverStatesRemotePromise;
}

export async function resetHostServerStateForTests(): Promise<void> {
  const remoteModel = await serverStatesRemotePromise;
  serverStatesRemotePromise = undefined;
  await remoteModel?.dispose();
}
