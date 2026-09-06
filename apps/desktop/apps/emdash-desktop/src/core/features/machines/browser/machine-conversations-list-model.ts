import { createListView, createTextMatcher, type ListSource } from '@emdash/ui/react/patterns';
import type { MachineConversationItem } from './machine-conversation-rows';

/**
 * The list-view state layer for the machine conversations list: an externally
 * owned source (the component bridges its query via `useQueryListSource`) plus
 * immediate client-side search across the title, provider, workspace path, and
 * resolved link names.
 */
export function createMachineConversationsListView(source: ListSource<MachineConversationItem>) {
  return createListView({
    getItemId: (item: MachineConversationItem) => item.conversation.id,
    source,
    search: {
      kind: 'sync',
      predicate: createTextMatcher(({ conversation }: MachineConversationItem) => [
        conversation.title,
        conversation.provider ?? '',
        conversation.workspacePath ?? '',
        conversation.taskName ?? '',
        conversation.projectName ?? '',
      ]),
    },
  });
}

export type MachineConversationsListViewModel = ReturnType<
  typeof createMachineConversationsListView
>;
