import type { HostRef } from '@emdash/core/primitives/host/api';
import type { McpProvidersResponse, McpServer } from '@emdash/core/primitives/mcp/api';
import { useToast } from '@emdash/ui/react/primitives';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import { useAgentInstallationStatuses } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import { useAgents } from '@core/features/agents/api/browser/use-agents';
import { getCatalogClient } from '@core/features/catalog/api/browser/client';
import { getMcpClient } from '@core/features/mcp/api/browser/client';
import { captureTelemetry } from '@core/primitives/telemetry/browser/telemetry-client';
import { useInstalledMcpServersLiveModel } from '../live-model-hooks';

const MCP_CATALOG_QUERY_KEY = ['mcp', 'catalog'] as const;

export function useMcps(host: HostRef) {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { data: installed, isLoading: isLoadingInstalled } = useInstalledMcpServersLiveModel(host);
  const { data: agents } = useAgents(host);
  const {
    data: agentStatuses,
    isPending: isLoadingAgentStatuses,
    probeAll,
  } = useAgentInstallationStatuses(host);

  // ── Queries ──────────────────────────────────────────────────────────

  const {
    data: catalog = [],
    isPending: isLoadingCatalog,
    refetch: reload,
  } = useQuery({
    queryKey: MCP_CATALOG_QUERY_KEY,
    queryFn: async () => {
      const client = await getCatalogClient();
      const result = await client.getMcpCatalog(undefined);
      if (result.success) return result.data;
      throw new Error(result.error.message);
    },
  });

  const providers = useMemo<McpProvidersResponse[]>(() => {
    const statusesById = new Map((agentStatuses ?? []).map((status) => [status.id, status]));
    return (agents ?? []).map((agent) => ({
      id: agent.id,
      name: agent.name,
      installed: statusesById.get(agent.id)?.status === 'available',
    }));
  }, [agents, agentStatuses]);

  const isLoading = isLoadingCatalog || isLoadingInstalled || isLoadingAgentStatuses;

  // ── Mutations ────────────────────────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: async (payload: { server: McpServer; source: 'catalog' | 'custom' | null }) => {
      const client = await getMcpClient();
      const result = await client.saveServer({ host, server: payload.server });
      if (!result.success) throw new Error(agentConfigErrorMessage(result.error));
    },
    onSuccess: (_, payload) => {
      if (payload.source) {
        captureTelemetry('mcp_server_added', { source: payload.source });
      }
    },
    onError: (error) => {
      toast.error('Failed to save server', { description: error.message });
    },
  });

  const saveServer = useCallback(
    async (server: McpServer, source: 'catalog' | 'custom' | null = null) => {
      await saveMutation.mutateAsync({ server, source });
    },
    [saveMutation]
  );

  const removeMutation = useMutation({
    mutationFn: async (serverName: string) => {
      const client = await getMcpClient();
      const result = await client.removeServer({ host, name: serverName });
      if (!result.success) throw new Error(agentConfigErrorMessage(result.error));
    },
    onSuccess: () => {
      captureTelemetry('mcp_server_removed');
    },
    onError: (error) => {
      toast.error('Failed to remove server', { description: error.message });
    },
  });

  const removeServer = useCallback(
    async (serverName: string) => {
      await removeMutation.mutateAsync(serverName);
    },
    [removeMutation]
  );

  const refreshMutation = useMutation({
    mutationFn: async () => {
      await new Promise<void>((resolve) => {
        probeAll(undefined, { onSettled: () => resolve() });
      });
      await queryClient.invalidateQueries({ queryKey: MCP_CATALOG_QUERY_KEY });
    },
    onError: () => {
      toast.error('Failed to refresh MCP data');
    },
  });

  const refresh = useCallback(() => refreshMutation.mutate(), [refreshMutation]);

  return {
    installed,
    catalog,
    providers,
    isLoading,
    isRefreshing: refreshMutation.isPending,
    saveServer,
    removeServer,
    refresh,
    reload,
  };
}

export type UseMcpsResult = ReturnType<typeof useMcps>;

function agentConfigErrorMessage(error: { type: string; message?: string; providerId?: string }) {
  return error.message ?? (error.providerId ? `Unknown provider: ${error.providerId}` : error.type);
}
