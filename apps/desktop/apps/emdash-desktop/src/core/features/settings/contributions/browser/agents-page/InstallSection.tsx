import { observer } from 'mobx-react-lite';
import { useEffect, useMemo, useState } from 'react';
import { hostRefFromConnectionId } from '@core/features/agents/api/browser/client';
import { useAgentInstallationStatus } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import { DependencyInstallationStatusCard } from '@core/features/settings/browser/agents-page/DependencyInstallationStatusCard';
import type { InstallationState } from '@core/features/settings/browser/agents-page/DependencyInstallationStatusCard';
import { DependencyInstallationUpdateCard } from '@core/features/settings/browser/agents-page/DependencyInstallationUpdateCard';
import {
  findInstallation,
  refFromUsed,
  toSelection,
} from '@core/features/settings/browser/agents-page/installation-sources';
import { InstallationOverrideCard } from '@core/features/settings/browser/agents-page/InstallationOverrideCard';
import { InstallDependencyCard } from '@core/features/settings/browser/agents-page/InstallDependencyCard';
import type {
  AgentPayload,
  Installation,
  InstallMethod,
  InstallOption,
  SelectedSource,
} from '@core/primitives/agents/api';
import { sourceKey } from '@core/primitives/agents/api';

export type InstallSectionProps = {
  agentId: string;
  /** SSH connection id; when provided, install/update/status operate on the remote host. */
  connectionId?: string;
  /** Full agent payload used to hydrate the hook before the first probe. */
  agentPayload: AgentPayload | undefined;
  /** Platform-specific install options from the agent payload. */
  installOptions: InstallOption[];
  /** Link to installation documentation, null if not set. */
  installDocs?: string | null;
  /** @deprecated No-op; override options are always visible in the source menu. */
  hideOverrideOptions?: boolean;
  compact?: boolean;
};

function isOverrideRef(
  ref: SelectedSource
): ref is { kind: 'path'; path: string } | { kind: 'cli'; command: string } {
  return ref.kind === 'path' || ref.kind === 'cli';
}

/**
 * Derives the initial selectedSource for an agent:
 *   1. A non-auto persisted override (user previously chose explicitly) — use it.
 *   2. Agent is uninstalled + a recommended install option exists — pre-select it.
 *   3. Otherwise fall back to auto.
 */
function seedSource(
  used: SelectedSource | undefined,
  status: string,
  installOptions: InstallOption[]
): SelectedSource {
  const liveRef = refFromUsed(used);
  if (liveRef.kind !== 'auto') return liveRef;
  if (status !== 'available') {
    const recommended = installOptions.find((o) => o.recommended);
    if (recommended) return { kind: 'method', method: recommended.method as InstallMethod };
  }
  return { kind: 'auto' };
}

/**
 * Status-driven composer that owns the renderer-local `selectedSource` (UI intent).
 * Selection is always persisted immediately — `used` and `selectedSource` are kept in sync.
 * Uninstalled agents with no prior override default to the recommended install method.
 */
export const InstallSection = observer(function InstallSection({
  agentId,
  connectionId,
  agentPayload,
  installOptions,
  installDocs,
  hideOverrideOptions,
  compact,
}: InstallSectionProps) {
  return (
    <LocalInstallSection
      agentId={agentId}
      connectionId={connectionId}
      agentPayload={agentPayload}
      installOptions={installOptions}
      installDocs={installDocs}
      hideOverrideOptions={hideOverrideOptions}
      compact={compact}
    />
  );
});

const LocalInstallSection = observer(function LocalInstallSection({
  agentId,
  connectionId,
  agentPayload,
  installOptions,
  installDocs: _installDocs,
  hideOverrideOptions: _hideOverrideOptions,
  compact = false,
}: InstallSectionProps) {
  const vm = useAgentInstallationStatus(
    agentId,
    hostRefFromConnectionId(connectionId),
    agentPayload
  );

  const [selectedSource, setSelectedSource] = useState<SelectedSource>(() =>
    seedSource(vm.used, vm.status, installOptions)
  );
  const [isChecking, setIsChecking] = useState(false);

  // Follow vm.used changes from background probes / post-install updates.
  // When vm.used is auto and the agent is not installed, keep the recommended
  // default instead of resetting — the user hasn't persisted a choice yet.
  useEffect(() => {
    if (vm.isInstalling || vm.isUpdating || !vm.used) return;
    const liveRef = refFromUsed(vm.used);
    if (liveRef.kind !== 'auto') {
      // Explicit persisted selection — always follow it
      setSelectedSource((prev) => (sourceKey(prev) !== sourceKey(liveRef) ? liveRef : prev));
    } else if (vm.status === 'available') {
      // Installed via auto (no explicit method) — reset to auto
      setSelectedSource((prev) => (prev.kind !== 'auto' ? { kind: 'auto' } : prev));
    }
    // Uninstalled + auto → keep the recommended pre-selection
  }, [vm.used, vm.status, vm.isInstalling, vm.isUpdating]);

  // Persisted override values used as initial inputs for the override card.
  const initialPath = useMemo(() => {
    const inst = vm.installations.find((i) => i.id === 'path');
    return inst?.pathEntry ?? '';
  }, [vm.installations]);

  const initialCli = useMemo(() => {
    const inst = vm.installations.find((i) => i.id === 'cli');
    return inst?.pathEntry ?? '';
  }, [vm.installations]);

  const selectedInstall = findInstallation(vm.installations, selectedSource);

  const isOverrideEmpty =
    isOverrideRef(selectedSource) &&
    ((selectedSource.kind === 'path' && !initialPath) ||
      (selectedSource.kind === 'cli' && !initialCli));

  const state: InstallationState = (() => {
    if (isChecking || vm.isInstalling) return 'checking';
    if (selectedInstall?.status === 'available') return 'found';
    if (isOverrideRef(selectedSource) && isOverrideEmpty) return 'uninstalled';
    return 'not-found';
  })();

  const onSelectSource = (ref: SelectedSource) => {
    // Persist every selection immediately so `used` always tracks `selected`,
    // including path/cli overrides. Empty overrides persist harmlessly —
    // resolveAgentExecutable falls back to auto-resolution when a path/cli
    // selection does not resolve, and onOverrideResolved re-persists the
    // concrete value once the user validates it.
    void vm.setUsed(toSelection(ref, { path: initialPath, cli: initialCli }));
    setSelectedSource(ref);
  };

  const onOverrideResolved = (installation: Installation | null) => {
    if (installation?.status === 'available') {
      void vm.setUsed(
        toSelection(selectedSource, {
          path: installation.id === 'path' ? (installation.pathEntry ?? '') : undefined,
          cli: installation.id === 'cli' ? (installation.pathEntry ?? '') : undefined,
        })
      );
    }
  };

  // For the install command card, narrow to the selected method when concrete.
  const effectiveInstallOptions = useMemo(() => {
    if (selectedSource.kind === 'method') {
      return installOptions.filter((o) => o.method === selectedSource.method);
    }
    return installOptions;
  }, [installOptions, selectedSource]);

  if (vm.runtimeError) {
    switch (vm.runtimeError.type) {
      case 'host-unavailable':
      case 'not-configured':
        return (
          <div
            role="alert"
            className="rounded-lg border border-border bg-background-secondary p-3 text-sm text-foreground-muted"
          >
            {vm.runtimeError.message}
          </div>
        );
    }
  }

  return (
    <div className="space-y-2">
      <DependencyInstallationStatusCard
        vm={vm}
        agentPayload={agentPayload}
        installOptions={installOptions}
        selectedSource={selectedSource}
        state={state}
        onSelectSource={onSelectSource}
      />

      {state === 'found' && (
        <DependencyInstallationUpdateCard
          agentId={agentId}
          agentPayload={agentPayload}
          compact={compact}
        />
      )}

      {state !== 'found' && !isOverrideRef(selectedSource) && (
        <InstallDependencyCard
          vm={vm}
          installOptions={effectiveInstallOptions}
          isInstalling={vm.isInstalling}
          installingMethod={vm.installingMethod}
          dependencyName={agentPayload?.name ?? agentId}
          compact={compact}
        />
      )}

      {state !== 'found' && isOverrideRef(selectedSource) && (
        <InstallationOverrideCard
          vm={vm}
          kind={selectedSource.kind}
          initialValue={selectedSource.kind === 'path' ? initialPath : initialCli}
          onChecking={setIsChecking}
          onResolved={onOverrideResolved}
        />
      )}
    </div>
  );
});
