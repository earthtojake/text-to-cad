import { DropdownMenu, toast } from '@emdash/ui/react/primitives';
import { Check, Loader2, MoreHorizontal, X } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import type { HostDependencyInstallation } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import type { AgentPayload, InstallOption, SelectedSource } from '@core/primitives/agents/api';
import { resolveActiveInstallation, sourceKey } from '@core/primitives/agents/api';
import { InstalledBadge, RecommendedBadge, UsedBadge } from './agent-status-badge';
import { buildSourceRows, provenanceLabel } from './installation-sources';

export type InstallationState = 'found' | 'not-found' | 'uninstalled' | 'checking';

export type DependencyInstallationStatusCardProps = {
  vm: HostDependencyInstallation;
  /** Full agent payload; used to detect when automatic updates are unavailable. */
  agentPayload?: AgentPayload;
  /** Platform-specific install options from the agent. */
  installOptions: InstallOption[];
  /** The currently selected source (renderer-local intent). */
  selectedSource: SelectedSource;
  /** The derived state to render. */
  state: InstallationState;
  /** Called when the user picks a different source from the menu. */
  onSelectSource: (ref: SelectedSource) => void;
};

export const DependencyInstallationStatusCard = observer(function DependencyInstallationStatusCard({
  vm,
  agentPayload,
  installOptions,
  selectedSource,
  state,
  onSelectSource,
}: DependencyInstallationStatusCardProps) {
  const { installations, refresh, fetchLatestVersion, uninstall, isUninstalling } = vm;

  const selectedInstall = resolveActiveInstallation(installations, selectedSource);
  const versionText =
    state === 'found' && selectedInstall?.version ? `v${selectedInstall.version}` : null;

  // Show the "no automatic updates" hint when the used installation is not manageable
  // for a package-manager strategy (i.e., we can't determine which PM to call).
  const updates = agentPayload?.capabilities.hostDependency.updates;
  const strategyKind = updates?.kind === 'supported' ? updates.update.kind : 'none';
  const showNoAutoUpdateHint =
    state === 'found' && !selectedInstall?.manageable && strategyKind === 'package-manager';

  const uninstallDescriptor = agentPayload?.capabilities.hostDependency.uninstall;
  const canUninstall =
    !!uninstallDescriptor && uninstallDescriptor.kind !== 'none' && state === 'found';

  const sourceRows = buildSourceRows(installOptions, installations);
  const selectedKey = sourceKey(selectedSource);
  const selectedRow = sourceRows.find((r) => sourceKey(r.ref) === selectedKey);

  // Build a human-readable label for the currently-selected source
  const selectedLabel = (() => {
    if (selectedInstall && selectedSource.kind !== 'auto') {
      const provLabel = provenanceLabel(selectedInstall.provenance);
      return selectedRow?.label ?? provLabel;
    }
    return selectedRow?.label ?? selectedSource.kind;
  })();

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-2 rounded-lg border p-3">
        {state === 'found' && (
          <div className="flex size-6 items-center justify-center rounded-lg bg-background-success">
            <Check
              className="size-3.5 shrink-0 text-foreground-success"
              absoluteStrokeWidth
              strokeWidth={3}
            />
          </div>
        )}
        {state === 'checking' && (
          <div className="flex size-6 items-center justify-center rounded-lg bg-background-2">
            <Loader2 className="size-3.5 animate-spin text-foreground-muted" />
          </div>
        )}
        {(state === 'not-found' || state === 'uninstalled') && (
          <div className="flex size-6 items-center justify-center rounded-lg bg-background-2">
            <X className="size-3.5 shrink-0 text-foreground-passive" strokeWidth={2.5} />
          </div>
        )}

        <div className="min-w-0 flex-1 truncate text-sm">
          {state === 'found' && (
            <>
              <span>Found</span>
              {versionText && (
                <span className="ml-1 rounded-md bg-background-quaternary-2 px-1 py-0.5 font-sans text-xs text-foreground-muted">
                  {versionText}
                </span>
              )}
              <span className="ml-1">installed using {selectedLabel}</span>
            </>
          )}
          {state === 'checking' && <span className="text-foreground-muted">Checking…</span>}
          {state === 'not-found' && (
            <span className="text-foreground-muted">Not found — install below</span>
          )}
          {state === 'uninstalled' && <span className="text-foreground-muted">Uninstalled</span>}
        </div>

        <DropdownMenu.Root>
          <DropdownMenu.Trigger
            className="shrink-0 rounded p-1 text-foreground-passive hover:bg-background-2 hover:text-foreground"
            aria-label="Installation options"
          >
            <MoreHorizontal className="h-3.5 w-3.5" />
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="end">
            <DropdownMenu.Sub>
              <DropdownMenu.SubTrigger>Change source</DropdownMenu.SubTrigger>
              <DropdownMenu.SubContent>
                <DropdownMenu.Group>
                  <DropdownMenu.Label>Select source</DropdownMenu.Label>
                  <DropdownMenu.Separator />
                  {sourceRows.map((row) => {
                    const rowKey = sourceKey(row.ref);
                    const isCurrentSource = rowKey === selectedKey;
                    return (
                      <DropdownMenu.Item key={rowKey} onClick={() => onSelectSource(row.ref)}>
                        <span className="flex items-center gap-1.5 truncate">
                          <span className="flex flex-col truncate">
                            <span className="truncate">{row.label}</span>
                            {row.displayPath && (
                              <span className="truncate font-mono text-xs text-foreground-muted">
                                {row.displayPath}
                              </span>
                            )}
                          </span>
                          {row.recommended && <RecommendedBadge />}
                          {/* "Installed" applies to concrete discovered binaries, never to the
                              'auto' policy row. Show it on every found installation, including
                              the currently-used one (which also gets the "Used" badge). */}
                          {row.status === 'available' && row.ref.kind !== 'auto' && (
                            <InstalledBadge />
                          )}
                          {isCurrentSource &&
                            (row.status === 'available' || selectedSource.kind !== 'auto') && (
                              <UsedBadge />
                            )}
                        </span>
                      </DropdownMenu.Item>
                    );
                  })}
                </DropdownMenu.Group>
              </DropdownMenu.SubContent>
            </DropdownMenu.Sub>
            <DropdownMenu.Separator />
            <DropdownMenu.Item
              onClick={() => {
                void toast.promise(refresh(), {
                  loading: 'Refreshing installations...',
                  success: 'Installations refreshed',
                  error: 'Failed to refresh installations',
                });
              }}
            >
              Refresh
            </DropdownMenu.Item>
            <DropdownMenu.Item
              onClick={() => {
                void toast.promise(fetchLatestVersion(), {
                  loading: 'Checking for updates...',
                  success: 'Checked for updates',
                  error: 'Failed to check for updates',
                });
              }}
            >
              Check for updates
            </DropdownMenu.Item>
            {canUninstall && (
              <>
                <DropdownMenu.Separator />
                <DropdownMenu.Item
                  variant="destructive"
                  disabled={isUninstalling}
                  onClick={() => {
                    const name = agentPayload?.name ?? 'Agent';
                    void toast.promise(uninstall(), {
                      loading: `Uninstalling ${name}...`,
                      success: `${name} successfully uninstalled`,
                      error: `Failed to uninstall ${name}`,
                    });
                  }}
                >
                  Uninstall
                </DropdownMenu.Item>
              </>
            )}
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </div>
      {showNoAutoUpdateHint && (
        <p className="px-1 text-xs text-foreground-muted">
          Automatic updates are not available for this installation.
        </p>
      )}
    </div>
  );
});
