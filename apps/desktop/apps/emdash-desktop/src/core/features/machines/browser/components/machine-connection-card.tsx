import { SettingsRow } from '@emdash/ui/react/patterns';
import { Button } from '@emdash/ui/react/primitives';
import { Cog, PlugIcon } from 'lucide-react';
import type { ConnectionState, SshConfig } from '@core/primitives/ssh/api';
import type { HostAvailabilityState } from '@core/services/hosts/api';
import { authLabel } from './machine-formatters';
import { MachineBadge } from './MachineBadge';

export function MachineConnectionRow({
  machine,
  state,
  availability,
  onEdit,
  onConnect,
  onRetry,
  onDisconnect,
}: {
  machine: SshConfig;
  state: ConnectionState;
  availability: HostAvailabilityState | undefined;
  onEdit: () => void;
  onConnect: () => void;
  onRetry: () => void;
  onDisconnect: () => void;
}) {
  const transportActive =
    state === 'connected' || state === 'connecting' || state === 'reconnecting';
  const preparing = availability?.kind === 'preparing';
  const ready = availability?.kind === 'ready';
  const retry = availability?.kind === 'unavailable' && availability.issue !== undefined;

  return (
    <SettingsRow
      label={
        <span className="flex items-center gap-2">
          SSH Connection
          <MachineBadge state={state} />
        </span>
      }
      description={
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span>
            {machine.host} · {machine.username} · {authLabel(machine)}
          </span>
        </span>
      }
      control={
        <span className="flex items-center gap-2">
          {availability && !ready && !preparing ? (
            <Button type="button" variant="primary" size="xs" onClick={retry ? onRetry : onConnect}>
              <PlugIcon />
              {retry ? 'Retry' : 'Connect'}
            </Button>
          ) : null}
          {transportActive || preparing ? (
            <Button type="button" variant="destructive" size="xs" onClick={onDisconnect}>
              Disconnect
            </Button>
          ) : null}
          <Button type="button" variant="secondary" size="xs" icon onClick={onEdit}>
            <Cog />
          </Button>
        </span>
      }
    />
  );
}
