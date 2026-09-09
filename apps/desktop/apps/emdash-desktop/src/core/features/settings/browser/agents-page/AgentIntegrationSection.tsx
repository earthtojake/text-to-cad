import type { HostRef } from '@emdash/core/primitives/host/api';
import { Button, Field, Label, Tooltip } from '@emdash/ui/react/primitives';
import { CheckCircle2, Clock3, ExternalLink, Info, Loader2 } from 'lucide-react';
import { useAgentHooksStatus } from '@core/features/agents/api/browser/use-agent-hooks-status';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { settingsViewDef } from '@core/features/settings/contributions/views';
import type { AgentPayload } from '@core/primitives/agents/api';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';

const HOME_PREFIX_RE = /^\/(?:Users|home)\/[^/]+/;

function tildify(absolutePath: string): string {
  return absolutePath.replace(HOME_PREFIX_RE, '~');
}

function InfoTooltip({ children }: { children: React.ReactNode }) {
  return (
    <Tooltip.Provider>
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <button
              type="button"
              className="text-foreground-muted hover:text-foreground"
              aria-label="More information"
            >
              <Info className="size-3.5" aria-hidden="true" />
            </button>
          }
        />
        <Tooltip.Content side="top" className="max-w-[260px] text-xs">
          {children}
        </Tooltip.Content>
      </Tooltip.Root>
    </Tooltip.Provider>
  );
}

export function AgentHooksSection({ agent, host }: { agent: AgentPayload; host: HostRef }) {
  const supportsHooks = agent.capabilities.hooks.kind !== 'none';
  const { status, isLoading } = useAgentHooksStatus(agent.id, host, supportsHooks);

  const showHooks = supportsHooks && (host.type !== 'remote' || isLoading || status !== undefined);
  if (!showHooks) return null;

  return (
    <Field.Root>
      <div className="flex items-center gap-1.5">
        <Label>Hooks</Label>
        <InfoTooltip>
          Hooks let Hardcore track agent status, deliver notifications, and capture session IDs for
          reliable resume.
        </InfoTooltip>
      </div>
      <div>
        {isLoading ? (
          <div className="flex h-6 items-center">
            <Loader2 className="size-3.5 animate-spin text-foreground-muted" />
          </div>
        ) : status?.state === 'installed' ? (
          <span
            className="flex items-center gap-1.5 text-xs text-foreground-muted"
            title={status.resolvedRoot}
          >
            <CheckCircle2 className="size-3.5 shrink-0 text-foreground-success" />
            Configured · {tildify(status.resolvedRoot)}
          </span>
        ) : (
          <span className="flex items-center gap-1.5 text-xs text-foreground-muted">
            <Clock3 className="size-3.5 shrink-0" />
            Configured on first session
          </span>
        )}
      </div>
    </Field.Root>
  );
}

export function AgentTrustSection({ agent }: { agent: AgentPayload }) {
  const supportsTrust = agent.capabilities.trust.kind !== 'none';
  const { value: taskSettings } = useAppSettingsKey('tasks');
  const { navigate } = useNavigate();

  if (!supportsTrust) return null;

  return (
    <Field.Root>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Label>Workspace Trust</Label>
          <InfoTooltip>Skip the folder trust prompt in supported CLIs for new tasks.</InfoTooltip>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 gap-1 px-2 text-xs"
          onClick={() => navigate(settingsViewDef({ tab: 'general' }))}
        >
          <ExternalLink className="size-3" aria-hidden="true" />
          Manage in Settings
        </Button>
      </div>
      <span className="flex items-center gap-1.5 text-xs text-foreground-muted">
        {taskSettings?.autoTrustWorktrees ? (
          <>
            <CheckCircle2 className="size-3.5 shrink-0 text-foreground-success" />
            Enabled
          </>
        ) : (
          'Disabled'
        )}
      </span>
    </Field.Root>
  );
}
