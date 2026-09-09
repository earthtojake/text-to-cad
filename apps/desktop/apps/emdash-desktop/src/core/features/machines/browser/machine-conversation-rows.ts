import type { HostConversationRow } from '@core/primitives/conversations/api';

/**
 * Presentation state of one cached host conversation record on the machine page
 * (spec §8). Orphan detection is inherently client-presentational (spec §7.5): a
 * record with no local task link is an orphan *from this client's view*.
 */
export type MachineConversationItem = {
  conversation: HostConversationRow;
  /** Has a client-side task link; orphans are rows without one. */
  linked: boolean;
  /** The host's last successful index read no longer contained this record. */
  missing: boolean;
  /**
   * The record's workspace association points at no known workspace of the host.
   * Only asserted when a workspace observation is available; `false` otherwise.
   */
  dangling: boolean;
  /** Tombstoned locally with the delete verb still in flight. */
  pendingRemoval: boolean;
};

export function joinMachineConversationRows(input: {
  conversations: readonly HostConversationRow[];
  /** Known workspace paths of the host, when a workspace observation is available. */
  knownWorkspacePaths?: ReadonlySet<string>;
}): MachineConversationItem[] {
  return input.conversations
    .map((conversation) => ({
      conversation,
      linked: conversation.taskId !== null,
      missing: conversation.observedStatus === 'missing',
      dangling:
        input.knownWorkspacePaths !== undefined &&
        conversation.workspacePath !== null &&
        !input.knownWorkspacePaths.has(conversation.workspacePath),
      pendingRemoval: conversation.pendingRemoval,
    }))
    .sort((a, b) => activityTimestamp(b.conversation) - activityTimestamp(a.conversation));
}

function activityTimestamp(conversation: HostConversationRow): number {
  const source = conversation.lastSessionActivityAt ?? conversation.updatedAt;
  const parsed = Date.parse(source);
  return Number.isNaN(parsed) ? 0 : parsed;
}
