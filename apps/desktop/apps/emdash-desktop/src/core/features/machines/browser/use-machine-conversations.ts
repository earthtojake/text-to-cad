import { useQuery } from '@tanstack/react-query';
import { getConversationsClient } from '@core/features/conversations/api/browser/client';
import type {
  HostConversationRow,
  HostConversationScope,
} from '@core/primitives/conversations/api';

export type MachineConversationsScope =
  | { kind: 'local' }
  | { kind: 'remote'; connectionId: string };

export function machineConversationsQueryKey(scope: MachineConversationsScope) {
  return ['machineConversations', scope.kind === 'local' ? 'local' : scope.connectionId] as const;
}

function toHostScope(scope: MachineConversationsScope): HostConversationScope {
  return scope.kind === 'local'
    ? { location: 'local', sshConnectionId: null }
    : { location: 'remote', sshConnectionId: scope.connectionId };
}

/**
 * The machine page's conversations read (spec §8). This reads the client registry —
 * a labeled cache, not the host — so it works while the host is unreachable.
 */
export function useMachineConversations(scope: MachineConversationsScope) {
  return useQuery({
    queryKey: machineConversationsQueryKey(scope),
    queryFn: async (): Promise<HostConversationRow[]> => {
      const client = await getConversationsClient();
      return client.listHostConversations(toHostScope(scope));
    },
    refetchOnWindowFocus: false,
    staleTime: 15_000,
  });
}

export async function linkMachineConversation(input: {
  conversationId: string;
  projectId: string;
  taskId: string;
}): Promise<void> {
  const client = await getConversationsClient();
  await client.linkConversationToTask(input);
}

export async function deleteMachineConversation(conversationId: string): Promise<void> {
  const client = await getConversationsClient();
  await client.deleteHostConversation({ conversationId });
}
