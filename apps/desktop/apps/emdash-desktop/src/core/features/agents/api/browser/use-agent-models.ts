import { hostRefKey } from '@emdash/core/primitives/host/api';
import { useQuery } from '@tanstack/react-query';
import { getAgentsClient, hostRefFromConnectionId, unwrapAgentsResult } from './client';
import { useAgents } from './use-agents';

/** The installed provider owns its model list; refresh it when a picker is reopened. */
export function useAgentModels(providerId: string | null, connectionId?: string) {
  const host = hostRefFromConnectionId(connectionId);
  const { data: agents } = useAgents(host);
  const agent = agents?.find((item) => item.id === providerId);
  const supportsDiscovery = agent?.capabilities.acp.kind === 'supported';
  const query = useQuery({
    queryKey: ['agent-models', hostRefKey(host), providerId],
    queryFn: async () => {
      if (!providerId) return [];
      return unwrapAgentsResult((await getAgentsClient()).discoverModels({ host, providerId }));
    },
    enabled: supportsDiscovery && agent?.status === 'available',
    staleTime: 60_000,
    retry: false,
  });
  const fallback = agent?.capabilities.models;
  const modelOptions = supportsDiscovery
    ? // The picker already has an unset/default choice; keep every named model.
      Object.fromEntries(
        (query.data ?? [])
          .filter(({ id }) => id !== 'default')
          .map(({ id, ...option }) => [id, option])
      )
    : fallback?.kind === 'selectable'
      ? fallback.modelOptions
      : null;
  return { modelOptions, isLoading: query.isFetching, error: query.error, refresh: query.refetch };
}
