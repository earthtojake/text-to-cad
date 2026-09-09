import { ExternalLink } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';
import type { AgentPayload } from '@core/primitives/agents/api';

function formatSupportsText(agent: AgentPayload): string {
  const supportsSessions = agent.capabilities.sessions.kind !== 'stateless';
  return `Supports: Prompts${supportsSessions ? ', Sessions' : ''}`;
}

export const AgentSheetHeaderSection = observer(function AgentSheetHeaderSection({
  agent,
}: {
  agent: AgentPayload;
}) {
  return (
    <div className="flex items-center gap-3">
      <div className="flex size-12 shrink-0 items-center justify-center rounded-lg bg-background-quaternary-1 p-1.5">
        <AgentIcon id={agent.id} size={24} />
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-lg text-foreground">{agent.name}</span>
          </div>

          {agent.websiteUrl && (
            <a
              href={agent.websiteUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md px-2 text-xs text-foreground-muted hover:bg-background-1 hover:text-foreground"
            >
              View Website
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>

        <span className="text-xs text-foreground-muted">{formatSupportsText(agent)}</span>
      </div>
    </div>
  );
});
