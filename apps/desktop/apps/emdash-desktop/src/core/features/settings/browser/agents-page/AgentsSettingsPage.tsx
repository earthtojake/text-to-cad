import React from 'react';
import { useSettingsSearch } from '@core/features/settings/browser/search/settings-search-context';
import { AgentsPanel } from '@core/features/settings/contributions/browser/agents-page/AgentsPanel';

export function AgentsSettingsPage() {
  const { query: settingsSearchQuery, setQuery: setSettingsSearchQuery } = useSettingsSearch();

  return (
    <AgentsPanel
      header={{ title: 'Agents', description: 'Manage agents and model configurations.' }}
      searchQuery={settingsSearchQuery}
      onSearchQueryChange={setSettingsSearchQuery}
    />
  );
}
