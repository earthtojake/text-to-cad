import type { HostRef } from '@emdash/core/primitives/host/api';
import { CardGridSection } from '@emdash/ui/react/components';
import { Loader2 } from 'lucide-react';
import React from 'react';
import { McpCard } from '@core/features/mcp/browser/components/McpCard';
import { McpDrawer, type McpDrawerMode } from '@core/features/mcp/browser/components/McpDrawer';
import type { UseMcpsResult } from '@core/features/mcp/browser/components/useMcps';
import { useOpenModal } from '@core/manifests/browser/modal-api';

type McpServersListProps = {
  mcp: UseMcpsResult;
  host: HostRef;
  search?: string;
  drawerMode: McpDrawerMode | null;
  onDrawerModeChange: (mode: McpDrawerMode | null) => void;
};

export const McpServersList: React.FC<McpServersListProps> = ({
  mcp,
  host,
  search = '',
  drawerMode,
  onDrawerModeChange,
}) => {
  const openConfirm = useOpenModal('confirmActionModal');

  const handleRemoveRequest = (serverName: string) => {
    onDrawerModeChange(null);
    void openConfirm({
      title: 'Remove MCP server?',
      description: `This will remove "${serverName}" from all agents. This action cannot be undone.`,
      confirmLabel: 'Remove',
    }).then((outcome) => {
      if (outcome.success) void mcp.removeServer(serverName);
    });
  };

  const drawerSource =
    drawerMode?.type === 'add-catalog'
      ? 'catalog'
      : drawerMode?.type === 'add-custom'
        ? 'custom'
        : null;

  const lowerSearch = search.toLowerCase();
  const installedNames = new Set(mcp.installed.map((server) => server.name));
  const filteredInstalled = mcp.installed.filter(
    (server) => !search || server.name.toLowerCase().includes(lowerSearch)
  );
  const filteredCatalog = mcp.catalog.filter(
    (entry) =>
      !installedNames.has(entry.key) &&
      (!search ||
        entry.name.toLowerCase().includes(lowerSearch) ||
        entry.description.toLowerCase().includes(lowerSearch))
  );

  if (mcp.isLoading) {
    return (
      <div className="flex min-h-64 items-center justify-center text-foreground">
        <Loader2 className="h-6 w-6 animate-spin text-foreground-muted" />
      </div>
    );
  }

  return (
    <div className="flex flex-col text-foreground">
      <McpDrawer
        open={drawerMode !== null}
        mode={drawerMode}
        host={host}
        providers={mcp.providers}
        onOpenChange={(open) => {
          if (!open) onDrawerModeChange(null);
        }}
        onSave={(server) => mcp.saveServer(server, drawerSource)}
        onRemove={handleRemoveRequest}
      />
      <div className="flex flex-col gap-8 py-8">
        {filteredInstalled.length > 0 && (
          <CardGridSection title="Added">
            {filteredInstalled.map((server) => (
              <McpCard
                key={server.name}
                server={server}
                providers={mcp.providers}
                catalogEntry={mcp.catalog.find((entry) => entry.key === server.name)}
                onEdit={(nextServer) => onDrawerModeChange({ type: 'edit', server: nextServer })}
              />
            ))}
          </CardGridSection>
        )}

        {filteredCatalog.length > 0 && (
          <CardGridSection title="Recommended">
            {filteredCatalog.map((entry) => (
              <McpCard
                key={entry.key}
                providers={mcp.providers}
                catalogEntry={entry}
                onAdd={(nextEntry) => onDrawerModeChange({ type: 'add-catalog', entry: nextEntry })}
              />
            ))}
          </CardGridSection>
        )}

        {filteredInstalled.length === 0 && filteredCatalog.length === 0 && (
          <div className="py-12 text-center">
            <p className="text-sm text-foreground-muted">
              {search ? 'No servers match your search.' : 'No servers available.'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
};
