import type { InstallMethod } from '@emdash/core/services/host-dependencies/api';
import { SettingsCard } from '@emdash/ui/react/patterns';
import { Box, Button, Field, Heading } from '@emdash/ui/react/primitives';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { useMemo } from 'react';
import type { MachineSystemDependencyStatus } from '@core/features/machines/api';
import { SudoRetryPanel } from '@core/primitives/agents/browser/SudoRetryPanel';
import type { DependencyOperationFailure } from '@core/primitives/host-dependencies/browser/use-dependency-operation-failures';
import type { SystemDependenciesStore } from '../machines-store';
import { useSystemDependencies } from '../use-system-dependencies';

type MachineSystemDependenciesCardProps = {
  machineId?: string;
  machinesStore: SystemDependenciesStore;
};

export function MachineSystemDependenciesCard({
  machineId,
  machinesStore,
}: MachineSystemDependenciesCardProps) {
  const {
    data,
    error,
    install,
    installAll,
    installFailures,
    dismissInstallFailure,
    installingIds,
    isInstalling,
    isLoading,
  } = useSystemDependencies(machineId, true, machinesStore);

  const dependencies = useMemo(
    () => [...(data ?? [])].sort((left, right) => left.name.localeCompare(right.name)),
    [data]
  );

  const requiredDependencies = useMemo(
    () => dependencies.filter((dependency) => dependency.tier === 'required'),
    [dependencies]
  );

  const recommendedDependencies = useMemo(
    () => dependencies.filter((dependency) => dependency.tier === 'recommended'),
    [dependencies]
  );

  const installableMissingDependencies = useMemo(
    () =>
      dependencies.filter(
        (dependency) => dependency.status !== 'available' && dependency.installOptions.length > 0
      ),
    [dependencies]
  );

  const canInstallAll = installableMissingDependencies.length > 0 && !isInstalling;

  return (
    <SettingsCard>
      <div className="flex items-center gap-2">
        <Field.Root>
          <Field.Label>System dependencies</Field.Label>
          <Field.Description>
            Host tools used by Hardcore and engineering workflows.
          </Field.Description>
        </Field.Root>
        <Button
          type="button"
          variant="primary"
          size="xs"
          disabled={!canInstallAll}
          onClick={() => void installAll(installableMissingDependencies)}
        >
          {isInstalling ? <Loader2 className="size-3.5 animate-spin" /> : 'Install all'}
        </Button>
      </div>
      <div className="mt-4">
        {isLoading ? (
          <div className="p-4 text-sm text-foreground-muted">Checking system dependencies...</div>
        ) : error ? (
          <div className="p-4 text-sm text-foreground-destructive">
            Failed to load system dependencies: {error.message}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <DependencySection
              title="Required"
              dependencies={requiredDependencies}
              installingIds={installingIds}
              installFailures={installFailures}
              onInstall={install}
              onDismissFailure={dismissInstallFailure}
            />
            <DependencySection
              title="Recommended"
              dependencies={recommendedDependencies}
              installingIds={installingIds}
              installFailures={installFailures}
              onInstall={install}
              onDismissFailure={dismissInstallFailure}
            />
          </div>
        )}
      </div>
    </SettingsCard>
  );
}

function DependencySection({
  title,
  dependencies,
  installingIds,
  installFailures,
  onInstall,
  onDismissFailure,
}: {
  title: string;
  dependencies: MachineSystemDependencyStatus[];
  installingIds: Set<string>;
  installFailures: Record<string, DependencyOperationFailure>;
  onInstall: (dependencyId: string, method?: InstallMethod, elevate?: boolean) => void;
  onDismissFailure: (dependencyId: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <Heading level={4} tone="muted">
        {title}
      </Heading>
      {dependencies.length === 0 ? (
        <div className="p-4 text-sm text-foreground-muted">
          No {title.toLowerCase()} dependencies.
        </div>
      ) : (
        <Box surface="sunken" borderRadius="md" padding="3">
          <div className="divide-y divide-border">
            {dependencies.map((dependency) => (
              <SystemDependencyRow
                key={dependency.id}
                dependency={dependency}
                installing={installingIds.has(dependency.id)}
                failure={installFailures[dependency.id] ?? null}
                onInstall={() => {
                  const option =
                    dependency.installOptions.find((candidate) => candidate.recommended) ??
                    dependency.installOptions[0];
                  onInstall(dependency.id, option?.method);
                }}
                onRetry={(method) => onInstall(dependency.id, method, true)}
                onDismissFailure={() => onDismissFailure(dependency.id)}
              />
            ))}
          </div>
        </Box>
      )}
    </div>
  );
}

function SystemDependencyRow({
  dependency,
  installing,
  failure,
  onInstall,
  onRetry,
  onDismissFailure,
}: {
  dependency: MachineSystemDependencyStatus;
  installing: boolean;
  failure: DependencyOperationFailure | null;
  onInstall: () => void;
  onRetry: (method?: InstallMethod) => void;
  onDismissFailure: () => void;
}) {
  const available = dependency.status === 'available';
  const canInstall = !available && dependency.installOptions.length > 0;

  return (
    <div className="space-y-2 py-1.5">
      <div className="flex h-10 min-w-0 items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs">{dependency.name}</div>
        </div>
        {available ? (
          <CheckCircle2 className="size-4 shrink-0 text-foreground-success" />
        ) : canInstall ? (
          <Button
            type="button"
            variant="secondary"
            size="xs"
            disabled={installing}
            onClick={onInstall}
          >
            {installing ? <Loader2 className="size-3.5 animate-spin" /> : 'Install'}
          </Button>
        ) : (
          <span className="shrink-0 text-xs text-foreground-muted">Not found</span>
        )}
      </div>
      {failure ? (
        <SudoRetryPanel
          error={failure.error}
          dependencyName={dependency.name}
          isRetrying={installing}
          onRetry={() => onRetry(failure.method)}
          onDismiss={onDismissFailure}
        />
      ) : null}
    </div>
  );
}
