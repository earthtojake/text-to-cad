import type { HostRef } from '@emdash/core/primitives/host/api';
import type { McpServer } from '@emdash/core/primitives/mcp/api';
import { useToast } from '@emdash/ui/react/primitives';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getMcpClient } from '@core/features/mcp/api/browser/client';

export function useAgentMcps(
  agentId: string,
  host: HostRef
): {
  servers: McpServer[];
  isLoading: boolean;
  removeServer: (name: string) => void;
  removingServerName: string | null;
} {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const queryKey = ['mcp', 'agent', host.type, host.id, agentId] as const;
  const { data: servers = [], isPending: isLoading } = useQuery({
    queryKey,
    queryFn: async () => {
      const result = await (await getMcpClient()).listForAgent({ host, providerId: agentId });
      if (result.success) return result.data.servers;
      throw new Error(configErrorMessage(result.error));
    },
  });

  const removeMutation = useMutation({
    mutationFn: async (name: string) => {
      const result = await (
        await getMcpClient()
      ).removeForAgent({
        host,
        providerId: agentId,
        name,
      });
      if (!result.success) throw new Error(configErrorMessage(result.error));
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey });
    },
    onError: (error) => {
      toast.error('Failed to remove MCP server', { description: error.message });
    },
  });

  return {
    servers,
    isLoading,
    removeServer: (name) => removeMutation.mutate(name),
    removingServerName: removeMutation.isPending ? (removeMutation.variables ?? null) : null,
  };
}

function configErrorMessage(error: { type: string; message?: string; providerId?: string }) {
  return error.message ?? (error.providerId ? `Unknown provider: ${error.providerId}` : error.type);
}
