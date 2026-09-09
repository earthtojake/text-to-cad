import type { HostRef } from '@emdash/core/primitives/host/api';
import type { McpServer } from '@emdash/core/primitives/mcp/api';
import { remote, type RemoteModel } from '@emdash/wire/state';
import { useMemo } from 'react';
import { getMcpClient } from '@core/features/mcp/api/browser/client';
import { useRemoteModelState } from '@core/primitives/wire/browser/use-remote-model-state';
import { mcpContract } from '../api';

let serversRemotePromise: Promise<RemoteModel<typeof mcpContract.servers>> | undefined;

export function useInstalledMcpServersLiveModel(host: HostRef): {
  data: McpServer[];
  isLoading: boolean;
} {
  const key = useMemo(() => ({ host }), [host]);
  const state = useRemoteModelState(mcpContract.servers, getServersRemote, key, 'list', {
    initialValue: [],
  });

  return { data: state.value ?? [], isLoading: state.isLoading };
}

function getServersRemote(): Promise<RemoteModel<typeof mcpContract.servers>> {
  serversRemotePromise ??= getMcpClient().then((client) =>
    remote(mcpContract.servers, client.servers, { lingerMs: 15_000 })
  );
  return serversRemotePromise;
}

export async function resetInstalledMcpServersLiveModelForTests(): Promise<void> {
  const remoteModel = await serversRemotePromise;
  serversRemotePromise = undefined;
  await remoteModel?.dispose();
}
