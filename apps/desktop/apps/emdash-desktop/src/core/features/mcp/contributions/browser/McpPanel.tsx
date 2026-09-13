import type { HostRef } from '@emdash/core/primitives/host/api';
import { PageLayout } from '@emdash/ui/react/patterns';
import React, { useState } from 'react';
import type { McpDrawerMode } from '@core/features/mcp/browser/components/McpDrawer';
import { McpServersList } from '@core/features/mcp/browser/components/McpServersList';
import { McpToolbar } from '@core/features/mcp/browser/components/McpToolbar';
import { useMcps } from '@core/features/mcp/browser/components/useMcps';

type McpPanelProps = {
  host: HostRef;
  header?: { title: string; description: string };
};

export function McpPanel({ host, header }: McpPanelProps) {
  const mcp = useMcps(host);
  const [search, setSearch] = useState('');
  const [drawerMode, setDrawerMode] = useState<McpDrawerMode | null>(null);

  const toolbar = (
    <McpToolbar
      search={search}
      onSearchChange={setSearch}
      onRefresh={mcp.refresh}
      isRefreshing={mcp.isRefreshing}
      onAddCustom={() => setDrawerMode({ type: 'add-custom' })}
    />
  );

  return (
    <div className="flex flex-col text-foreground">
      {header ? (
        <PageLayout.Header
          sticky
          title={header.title}
          description={header.description}
          actions={toolbar}
        />
      ) : (
        toolbar
      )}
      <McpServersList
        mcp={mcp}
        host={host}
        search={search}
        drawerMode={drawerMode}
        onDrawerModeChange={setDrawerMode}
      />
    </div>
  );
}
