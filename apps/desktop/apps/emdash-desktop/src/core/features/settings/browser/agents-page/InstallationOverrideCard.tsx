import { Alert, Input } from '@emdash/ui/react/primitives';
import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import type { HostDependencyInstallation } from '@core/features/agents/api/browser/use-agent-installation-statuses';
import type { Installation } from '@core/primitives/agents/api';
import { CommandActionButton } from '@core/primitives/agents/browser/install-command-row';

export type InstallationOverrideCardProps = {
  vm: HostDependencyInstallation;
  kind: 'path' | 'cli';
  /** Initial value from persisted selection, if any. */
  initialValue?: string;
  /** Called when checking state changes (for parent to derive 'checking' state). */
  onChecking: (isChecking: boolean) => void;
  /** Called with the probe result once Validate completes (null means probeOverride returned nothing). */
  onResolved: (installation: Installation | null) => void;
};

export function InstallationOverrideCard({
  vm,
  kind,
  initialValue = '',
  onChecking,
  onResolved,
}: InstallationOverrideCardProps) {
  const [value, setValue] = useState(initialValue);
  const [isChecking, setIsChecking] = useState(false);

  const handleValidate = async () => {
    setIsChecking(true);
    onChecking(true);
    try {
      const selection = kind === 'path' ? { path: value } : { cli: value };
      const result = await vm.probeOverride(selection);
      onResolved(result ?? null);
    } finally {
      setIsChecking(false);
      onChecking(false);
    }
  };

  const hasValue = value.trim().length > 0;

  return (
    <div className="space-y-2 rounded-lg border p-3">
      <Input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={
          kind === 'path' ? '/usr/local/bin/claude' : kind === 'cli' ? 'claude' : undefined
        }
        className="font-mono text-sm"
        disabled={isChecking}
      />
      <Alert.Root status="warning">
        {kind === 'path'
          ? "Using an absolute path to the agent binary overrides auto-resolution and disables Hardcore's ability to update the agent."
          : "Enter the command name or binary resolved on PATH. This overrides auto-resolution and disables Hardcore's ability to update the agent."}
      </Alert.Root>
      {hasValue && (
        <div className="flex justify-end">
          <CommandActionButton disabled={isChecking} onClick={() => void handleValidate()}>
            {isChecking ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : 'Validate'}
          </CommandActionButton>
        </div>
      )}
    </div>
  );
}
