import { CollectionView, useQueryListSource } from '@emdash/ui/react/patterns';
import { BotIcon } from 'lucide-react';
import React, { useLayoutEffect, useState } from 'react';
import { hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import { useAgents } from '@core/features/agents/api/browser/use-agents';
import { AgentDetailSheet } from '@core/features/settings/browser/agents-page/AgentDetailSheet';
import { AgentRow } from '@core/features/settings/browser/agents-page/AgentRow';
import { createAgentsListView } from '@core/features/settings/browser/agents-page/agents-list-model';
import type { AgentPayload } from '@core/primitives/agents/api';

type CliAgentsListProps = {
  searchQuery?: string;
  connectionId?: string;
  onManageMcp?: () => void;
  /** Sticky toolbar row rendered inside the list card. */
  toolbar?: React.ReactNode;
};

export const CliAgentsList: React.FC<CliAgentsListProps> = ({
  searchQuery = '',
  connectionId,
  onManageMcp,
  toolbar,
}) => {
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const host = hostRefFromConnectionId(connectionId);
  const agentsQuery = useAgents(host);

  const source = useQueryListSource(agentsQuery, (agents: AgentPayload[]) => agents);
  const [view] = useState(() => createAgentsListView(source));

  // The search query is owned outside the view (settings search context or the
  // panel's local state); mirror it into the view's search slice.
  useLayoutEffect(() => {
    view.store.search?.setQuery(searchQuery);
  }, [searchQuery, view]);

  const hasAgents = (agentsQuery.data?.length ?? 0) > 0;

  return (
    <>
      <view.Root>
        <CollectionView
          view={view}
          renderRow={(agent) => <AgentRow agent={agent} />}
          density="compact"
          toolbar={toolbar}
          onItemClick={(agent) => setSelectedAgentId(agent.id)}
          emptySlot={<AgentsEmptyState hasAgents={hasAgents} />}
        />
      </view.Root>
      <AgentDetailSheet
        agentId={selectedAgentId}
        connectionId={connectionId}
        onManageMcp={onManageMcp}
        onClose={() => setSelectedAgentId(null)}
      />
    </>
  );
};

// Icon-bearing empty state — `EmptyState` has no icon slot, so this stays
// custom under the rich-states carve-out.
function AgentsEmptyState({ hasAgents }: { hasAgents: boolean }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center p-8 text-center">
      <BotIcon className="mb-3 size-8 text-foreground-passive" />
      <div className="text-sm text-foreground">
        {hasAgents ? 'No agents match your search' : 'No agents'}
      </div>
      <p className="mt-1 max-w-sm text-xs text-foreground-passive">
        {hasAgents
          ? 'Try a different agent name.'
          : 'Agents appear here once they can be detected on this machine.'}
      </p>
    </div>
  );
}
