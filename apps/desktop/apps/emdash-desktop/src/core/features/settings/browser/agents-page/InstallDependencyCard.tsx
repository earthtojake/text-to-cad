import { Loader2 } from 'lucide-react';
import type { HostDependencyInstallation } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import type { InstallMethod, InstallOption } from '@core/primitives/agents/api';
import {
  CommandActionButton,
  CommandRow,
} from '@core/primitives/agents/browser/install-command-row';
import { SudoRetryPanel } from '@core/primitives/agents/browser/SudoRetryPanel';
import { cn } from '@core/primitives/styling/browser/cn';

export type InstallDependencyCardProps = {
  vm: HostDependencyInstallation;
  /** The filtered install options to display. Parent passes the relevant method(s). */
  installOptions: InstallOption[];
  /** Whether an install is currently in progress (any method). */
  isInstalling?: boolean;
  /** The install method currently being installed, if any. */
  installingMethod?: InstallMethod;
  dependencyName?: string;
  compact?: boolean;
  /** Additional class name for the container. */
  className?: string;
};

/**
 * Renders one or more install command rows for the provided install options.
 * Source selection is owned by InstallSection; this card only fires vm.install.
 */
export function InstallDependencyCard({
  vm,
  installOptions,
  isInstalling = false,
  installingMethod,
  dependencyName,
  compact = false,
  className,
}: InstallDependencyCardProps) {
  const { install } = vm;

  if (installOptions.length === 0) return null;

  return (
    <div className={cn('space-y-2 rounded-lg border p-3', className)}>
      <div className="text-sm text-foreground-muted">Install</div>
      {installOptions.map((opt) => {
        const isInstallingThis =
          isInstalling && (installingMethod === undefined || installingMethod === opt.method);
        const failure =
          vm.installFailure &&
          (vm.installFailure.method === undefined || vm.installFailure.method === opt.method)
            ? vm.installFailure
            : null;
        return (
          <div key={opt.method} className="space-y-2">
            <CommandRow
              command={opt.command}
              action={
                <CommandActionButton
                  disabled={isInstalling}
                  onClick={() => void install(opt.method)}
                >
                  {isInstallingThis ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Install'}
                </CommandActionButton>
              }
            />
            {failure ? (
              <SudoRetryPanel
                error={failure.error}
                dependencyName={dependencyName ?? vm.data?.id ?? 'this dependency'}
                isRetrying={isInstallingThis}
                onRetry={() => void install(opt.method, true)}
                onDismiss={vm.dismissInstallFailure}
                compact={compact}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
