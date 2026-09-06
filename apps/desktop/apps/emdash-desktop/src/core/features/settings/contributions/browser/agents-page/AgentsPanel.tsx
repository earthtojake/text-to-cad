import { PageLayout } from '@emdash/ui/react/patterns';
import React, { useCallback, useMemo, useState } from 'react';
import { hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import { useAgentInstallationStatuses } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import { AgentsToolbar } from '@core/features/settings/browser/agents-page/AgentsToolbar';
import { CliAgentsList } from '@core/features/settings/browser/agents-page/CliAgentsList';

type AgentsPanelProps = {
  connectionId?: string;
  header?: { title: string; description: string };
  searchQuery?: string;
  onSearchQueryChange?: (query: string) => void;
  onManageMcp?: () => void;
};

export function AgentsPanel({
  connectionId,
  header,
  searchQuery: controlledSearchQuery,
  onSearchQueryChange,
  onManageMcp,
}: AgentsPanelProps) {
  const host = useMemo(() => hostRefFromConnectionId(connectionId), [connectionId]);
  const [localSearchQuery, setLocalSearchQuery] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const { probeAll } = useAgentInstallationStatuses(host);
  const searchQuery = controlledSearchQuery ?? localSearchQuery;
  const setSearchQuery = onSearchQueryChange ?? setLocalSearchQuery;

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    probeAll(undefined, {
      onSettled: () => setRefreshing(false),
    });
  }, [probeAll]);

  const list = (
    <CliAgentsList
      searchQuery={searchQuery}
      connectionId={connectionId}
      onManageMcp={onManageMcp}
      toolbar={
        <AgentsToolbar
          searchQuery={searchQuery}
          onSearchQueryChange={setSearchQuery}
          onRefresh={handleRefresh}
          isRefreshing={refreshing}
        />
      }
    />
  );

  if (header) {
    return (
      <div className="flex min-h-0 flex-col gap-4">
        <PageLayout.Header sticky title={header.title} description={header.description} />
        {list}
      </div>
    );
  }

  return list;
}
