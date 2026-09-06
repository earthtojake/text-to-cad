import type { HostRef } from '@emdash/core/primitives/host/api';
import type { HooksStatus } from '@emdash/core/runtimes/agent-config/api';
import { useQuery } from '@tanstack/react-query';
import { getAgentsClient, unwrapAgentsResult } from './client';

export function useAgentHooksStatus(
  providerId: string,
  host: HostRef,
  enabled: boolean
): { status: HooksStatus | undefined; isLoading: boolean; isError: boolean } {
  const { data, isError, isPending } = useQuery({
    queryKey: ['agents', 'hooks-status', host.type, host.id, providerId],
    enabled,
    queryFn: async () =>
      unwrapAgentsResult((await getAgentsClient()).hooksStatus({ host, providerId })),
  });

  return { status: data, isLoading: enabled && isPending, isError };
}
