import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import type { TerminalShellAvailability } from '@emdash/core/primitives/terminal-shell/api';
import { useQuery } from '@tanstack/react-query';
import { getTerminalsClient } from '@core/features/terminals/api/browser/client';

export const DEFAULT_TERMINAL_SHELL_AVAILABILITY: TerminalShellAvailability[] = [];

export function useTerminalShellAvailability(
  remoteConnectionId: string | undefined,
  options: { enabled?: boolean } = {}
) {
  const isRemote = Boolean(remoteConnectionId);
  const host = remoteConnectionId ? hostRef('remote', remoteConnectionId) : LOCAL_HOST_REF;
  return useQuery({
    queryKey: ['terminal-shell-availability', remoteConnectionId ?? 'local'],
    queryFn: async () => {
      const result = await (await getTerminalsClient()).getShellAvailability({ host });
      if (!result.success) {
        throw new Error(
          'message' in result.error
            ? result.error.message
            : `Terminal shell lookup failed: ${result.error.type}`
        );
      }
      return result.data;
    },
    staleTime: isRemote ? 5_000 : 30_000,
    enabled: options.enabled ?? true,
  });
}
