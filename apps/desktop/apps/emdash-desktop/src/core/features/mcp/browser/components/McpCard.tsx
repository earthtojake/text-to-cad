import type {
  McpCatalogEntry,
  McpProvidersResponse,
  McpServer,
} from '@emdash/core/primitives/mcp/api';
import type { AgentProviderId } from '@emdash/plugins/agents/types';
import { CardGridItem } from '@emdash/ui/react/components';
import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { ExternalLink, Globe, Pencil, Plus, Terminal } from 'lucide-react';
import React from 'react';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';
import { McpServerIcon } from '@core/features/mcp/browser/mcpIcons';

interface McpCardProps {
  server?: McpServer;
  /** Host-scoped provider list from the owning panel's `useMcps(host)`. */
  providers: McpProvidersResponse[];
  catalogEntry?: McpCatalogEntry;
  onEdit?: (server: McpServer) => void;
  onAdd?: (entry: McpCatalogEntry) => void;
}

const MAX_VISIBLE_PROVIDERS = 5;

function getTransport(server?: McpServer, entry?: McpCatalogEntry): 'stdio' | 'http' {
  if (server) return server.transport;
  const cfg = entry?.defaultConfig;
  if (cfg?.type === 'http' || (cfg && 'url' in cfg && !('command' in cfg))) return 'http';
  return 'stdio';
}

export const McpCard: React.FC<McpCardProps> = ({
  server,
  providers,
  catalogEntry,
  onEdit,
  onAdd,
}) => {
  const name = server?.name ?? catalogEntry?.name ?? 'Unknown';
  const description = catalogEntry?.description ?? (server ? `${server.transport} server` : '');
  const isInstalled = !!server;
  const transport = getTransport(server, catalogEntry);
  const docsUrl = catalogEntry?.docsUrl;
  const agentIds = new Set(providers.map((provider) => provider.id));
  const syncedProviders = (server?.providers ?? []).filter((id) =>
    agentIds.has(id)
  ) as AgentProviderId[];
  const visibleProviders = syncedProviders.slice(0, MAX_VISIBLE_PROVIDERS);
  const hiddenProviderCount = syncedProviders.length - visibleProviders.length;

  const handleClick = () => {
    if (isInstalled && server && onEdit) {
      onEdit(server);
    } else if (catalogEntry && onAdd) {
      onAdd(catalogEntry);
    }
  };

  return (
    <CardGridItem
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          handleClick();
        }
      }}
      className="group relative"
    >
      <McpServerIcon name={name} iconKey={catalogEntry?.key ?? server?.name} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex min-w-0 items-center gap-2">
          <h3 className="text-smd min-w-0 truncate">{name}</h3>
          <span className="inline-flex shrink-0 items-center gap-0.5 rounded bg-background-2 px-1 py-0.5 text-micro text-foreground-muted">
            {transport === 'http' ? <Globe className="size-2" /> : <Terminal className="size-2" />}
            {transport}
          </span>
        </div>
        {description && <p className="line-clamp-1 text-xs text-foreground-muted">{description}</p>}
        {syncedProviders.length > 0 && (
          <div className="mt-1.5 flex flex-wrap items-center gap-1">
            {visibleProviders.map((id) => (
              <AgentIcon key={id} id={id} size={14} className="rounded-sm" />
            ))}
            {hiddenProviderCount > 0 && (
              <span className="text-micro leading-none text-foreground-muted">
                +{hiddenProviderCount}
              </span>
            )}
          </div>
        )}
      </div>

      <div className="absolute inset-y-0 right-0 flex items-center gap-1 rounded-r-lg bg-linear-to-r from-transparent to-background-2 pr-3 pl-10 opacity-0 transition-opacity group-hover:opacity-100">
        {docsUrl && (
          <Tooltip.Root>
            <Tooltip.Trigger
              render={
                <Button
                  size="sm"
                  icon
                  variant="ghost"
                  onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                    e.stopPropagation();
                    window.open(docsUrl, '_blank', 'noopener,noreferrer');
                  }}
                  aria-label={`View ${name} docs`}
                >
                  <ExternalLink className="h-4 w-4" />
                </Button>
              }
            />
            <Tooltip.Content>View docs</Tooltip.Content>
          </Tooltip.Root>
        )}
        <Tooltip.Root>
          <Tooltip.Trigger
            render={
              <Button
                size="sm"
                icon
                variant="ghost"
                onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                  e.stopPropagation();
                  if (isInstalled && server && onEdit) {
                    onEdit(server);
                  } else if (catalogEntry && onAdd) {
                    onAdd(catalogEntry);
                  }
                }}
                aria-label={isInstalled ? `Edit ${name}` : `Add ${name}`}
              >
                {isInstalled ? <Pencil className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              </Button>
            }
          />
          <Tooltip.Content>{isInstalled ? 'Edit' : 'Add'}</Tooltip.Content>
        </Tooltip.Root>
      </div>
    </CardGridItem>
  );
};
