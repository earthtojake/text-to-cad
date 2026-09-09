import { hostRefKey, type HostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeResolveError } from '@emdash/core/services/runtime-broker/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getAgentsClient, unwrapAgentsResult } from '@core/features/agents/api/browser/client';
import type { AgentSettings } from '@core/primitives/agents/api';
import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';

function agentSettingsQueryKey(id: string, host: HostRef) {
  return ['agents', 'settings', hostRefKey(host), id] as const;
}

export function useAgentSettings(id: string, host: HostRef) {
  const queryClient = useQueryClient();
  const queryKey = agentSettingsQueryKey(id, host);

  const query = useQuery<AgentSettings | null, RuntimeResolveError>({
    queryKey,
    queryFn: async () => unwrapAgentsResult((await getAgentsClient()).getSettings({ host, id })),
    staleTime: 60_000,
  });

  const updateMutation = useMutation<void, RuntimeResolveError, Partial<ProviderCustomConfig>>({
    mutationFn: async (config) =>
      unwrapAgentsResult((await getAgentsClient()).updateSettings({ host, id, config })),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const resetMutation = useMutation<void, RuntimeResolveError, void>({
    mutationFn: async () => {
      const client = await getAgentsClient();
      const defaults = await unwrapAgentsResult(client.getDefaultSettings({ host, id }));
      if (defaults) {
        await unwrapAgentsResult(client.updateSettings({ host, id, config: defaults }));
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const { data } = query;
  return {
    ...query,
    value: data?.value,
    defaults: data?.defaults,
    overrides: data?.overrides,
    isSaving: updateMutation.isPending || resetMutation.isPending,
    isOverridden: !!(data?.overrides && Object.keys(data.overrides).length > 0),
    isFieldOverridden: (field: keyof ProviderCustomConfig) =>
      !!(data?.overrides && field in data.overrides),
    update: updateMutation.mutate,
    updateAsync: updateMutation.mutateAsync,
    reset: resetMutation.mutate,
  };
}
