import type { HostRef } from '@emdash/core/primitives/host/api';
import type { McpServer } from '@emdash/core/primitives/mcp/api';
import { Button, Field, Label } from '@emdash/ui/react/primitives';
import { ExternalLink, Globe, Loader2, Terminal, X } from 'lucide-react';
import React from 'react';
import { useAgentMcps } from '@core/features/agents/api/browser/use-agent-mcps';
import { settingsViewDef } from '@core/features/settings/contributions/views';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';

function McpServerPill({
  server,
  isRemoving,
  onRemove,
}: {
  server: McpServer;
  isRemoving: boolean;
  onRemove: () => void;
}) {
  const Icon = server.transport === 'http' ? Globe : Terminal;

  return (
    <span
      className="group inline-flex h-8 max-w-full items-center gap-1.5 rounded-lg border border-border bg-background-quaternary-1 pr-1.5 pl-3 text-xs text-foreground transition-colors hover:border-border-destructive/60 hover:bg-background-destructive hover:text-foreground-destructive"
      title={`${server.name} (${server.transport})`}
    >
      <Icon
        className="size-3.5 shrink-0 text-foreground-muted transition-opacity group-hover:opacity-35"
        aria-hidden="true"
      />
      <span className="min-w-0 truncate font-medium transition-opacity group-hover:opacity-35">
        {server.name}
      </span>
      <span className="shrink-0 text-foreground-muted transition-opacity group-hover:opacity-35">
        {server.transport}
      </span>
      <button
        type="button"
        disabled={isRemoving}
        className="inline-flex size-5 shrink-0 items-center justify-center rounded-md text-foreground-muted opacity-0 transition-[background-color,color,opacity] group-hover:opacity-100 hover:bg-background-destructive hover:text-foreground-destructive disabled:opacity-60"
        onClick={onRemove}
        aria-label={`Remove ${server.name} from this agent`}
      >
        {isRemoving ? (
          <Loader2 className="size-3 animate-spin" aria-hidden="true" />
        ) : (
          <X className="size-3" aria-hidden="true" />
        )}
      </button>
    </span>
  );
}

function EmptyMcpState() {
  return (
    <p className="text-xs text-foreground-muted">No MCP servers configured for this agent yet.</p>
  );
}

export function useManageMcpSettingsNavigation(): () => void {
  const { navigate } = useNavigate();
  return () => navigate(settingsViewDef({ tab: 'mcp' }));
}

export function AgentMcpSection({
  agentId,
  host,
  onManage,
}: {
  agentId: string;
  host: HostRef;
  onManage?: () => void;
}) {
  const { servers, isLoading, removeServer, removingServerName } = useAgentMcps(agentId, host);

  return (
    <Field.Root>
      <div className="flex items-center justify-between">
        <Label>MCP Servers</Label>
        {onManage && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-6 gap-1 px-2 text-xs"
            onClick={onManage}
          >
            <ExternalLink className="size-3" aria-hidden="true" />
            Manage in Settings
          </Button>
        )}
      </div>
      <div>
        {isLoading ? (
          <div className="flex h-9 items-center justify-center">
            <Loader2 className="size-4 animate-spin text-foreground-muted" />
          </div>
        ) : servers.length === 0 ? (
          <EmptyMcpState />
        ) : (
          <div className="flex flex-wrap gap-2">
            {servers.map((server) => (
              <McpServerPill
                key={server.name}
                server={server}
                isRemoving={removingServerName === server.name}
                onRemove={() => removeServer(server.name)}
              />
            ))}
          </div>
        )}
      </div>
    </Field.Root>
  );
}
