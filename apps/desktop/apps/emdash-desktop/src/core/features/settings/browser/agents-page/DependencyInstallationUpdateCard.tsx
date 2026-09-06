import { ArrowRight, Loader2, RefreshCw } from 'lucide-react';
import { useMemo } from 'react';
import { hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import { useAgentInstallationStatus } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import type { AgentPayload, InstallMethod } from '@core/primitives/agents/api';
import { resolveActiveInstallation } from '@core/primitives/agents/api';
import {
  CommandActionButton,
  CommandRow,
} from '@core/primitives/agents/browser/install-command-row';
import { SudoRetryPanel } from '@core/primitives/agents/browser/SudoRetryPanel';

export type DependencyInstallationUpdateCardProps = {
  agentId: string;
  /** SSH connection id; when provided, the update operates on the remote host. */
  connectionId?: string;
  /** Full agent payload used to hydrate the hook and derive the update strategy. */
  agentPayload: AgentPayload | undefined;
  compact?: boolean;
};

/**
 * Self-contained update card for a single agent dependency. Reads the
 * host-scoped installation state via useAgentInstallationStatus and renders
 * the update action for the currently used installation when an update is
 * available. Renders nothing when no update is applicable.
 *
 * Strategy-aware:
 * - package-manager: shows the per-method updateCommand (or re-runs `command`),
 *   calls update(method).
 * - cli: shows `<binary> <args>` and calls update() with no method (the binary
 *   self-updates; works for any source including 'unknown').
 * - auto / none: renders nothing.
 */
export function DependencyInstallationUpdateCard({
  agentId,
  connectionId,
  agentPayload,
  compact = false,
}: DependencyInstallationUpdateCardProps) {
  const vm = useAgentInstallationStatus(
    agentId,
    hostRefFromConnectionId(connectionId),
    agentPayload
  );
  const { used, installations, update, isUpdating, updatingMethod, updateFailure } = vm;

  const updates = agentPayload?.capabilities.hostDependency.updates;
  const strategyKind = updates?.kind === 'supported' ? updates.update.kind : ('none' as const);

  // Resolve the Installation for the currently used source
  const usedInstallation = useMemo(() => {
    if (!used) return undefined;
    return resolveActiveInstallation(installations, used);
  }, [used, installations]);

  // Build a map of method -> updateCommand for package-manager strategy
  const updateCommands = useMemo(() => {
    const map: Record<string, string> = {};
    for (const opt of agentPayload?.installOptions ?? []) {
      if (opt.updateCommand) {
        map[opt.method] = opt.updateCommand;
      }
    }
    return map;
  }, [agentPayload]);

  if (!usedInstallation?.updateAvailable) return null;
  if (strategyKind === 'auto' || strategyKind === 'none') return null;

  const versionArrow =
    usedInstallation.version && usedInstallation.latestVersion ? (
      <span className="flex items-center gap-1 text-xs text-foreground-muted">
        <span className="font-sans">{usedInstallation.version}</span>
        <ArrowRight className="h-3 w-3 shrink-0" />
        <span className="font-sans">{usedInstallation.latestVersion}</span>
      </span>
    ) : null;

  if (strategyKind === 'package-manager') {
    // Determine the effective method from the installation's confirmed provenance.
    // If not manageable, updateAvailable would already be false, so this is a guard.
    if (!usedInstallation.manageable) return null;

    const provKind = usedInstallation.provenance.kind;
    const usedMethod =
      provKind !== 'manual' && provKind !== 'version-manager' && provKind !== 'unknown'
        ? (provKind as InstallMethod)
        : null;
    if (!usedMethod) return null;

    // Prefer explicit updateCommand; fall back to the install command for that method
    const installOption = agentPayload?.installOptions.find((o) => o.method === usedMethod);
    const command = updateCommands[usedMethod] ?? installOption?.command ?? null;
    if (!command) return null;

    const isUpdatingThis =
      isUpdating && (updatingMethod === undefined || updatingMethod === usedMethod);

    return (
      <UpdateCard versionArrow={versionArrow}>
        <CommandRow
          command={command}
          action={
            <CommandActionButton
              disabled={isUpdatingThis}
              onClick={() => void update(usedMethod as InstallMethod)}
            >
              {isUpdatingThis ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Update'}
            </CommandActionButton>
          }
        />
        {updateFailure &&
        (updateFailure.method === undefined || updateFailure.method === usedMethod) ? (
          <SudoRetryPanel
            error={updateFailure.error}
            dependencyName={agentPayload?.name ?? agentId}
            isRetrying={isUpdatingThis}
            onRetry={() => void update(usedMethod, true)}
            onDismiss={vm.dismissUpdateFailure}
            compact={compact}
          />
        ) : null}
      </UpdateCard>
    );
  }

  // cli strategy — binary self-updates regardless of install source
  if (strategyKind === 'cli' && updates?.kind === 'supported' && updates.update.kind === 'cli') {
    const cliUpdate = updates.update;
    const binary = usedInstallation.pathEntry ?? agentPayload?.id ?? agentId;
    const command = [binary, ...cliUpdate.args].join(' ');
    const isUpdatingThis = isUpdating && updatingMethod === undefined;

    return (
      <UpdateCard versionArrow={versionArrow}>
        <CommandRow
          command={command}
          action={
            <CommandActionButton disabled={isUpdatingThis} onClick={() => void update()}>
              {isUpdatingThis ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Update'}
            </CommandActionButton>
          }
        />
      </UpdateCard>
    );
  }

  return null;
}

function UpdateCard({
  versionArrow,
  children,
}: {
  versionArrow: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2 rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex size-6 items-center justify-center rounded-lg bg-background-warning">
            <RefreshCw
              className="size-3.5 shrink-0 text-foreground-warning"
              absoluteStrokeWidth
              strokeWidth={3}
            />
          </div>
          <span>Update available</span>
        </div>
        {versionArrow}
      </div>
      {children}
    </div>
  );
}
