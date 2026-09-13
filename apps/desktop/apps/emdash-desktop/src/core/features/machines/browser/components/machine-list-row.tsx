import { MachineStatus } from '@emdash/ui/react/components';
import { observer } from 'mobx-react-lite';
import type { SshConfig } from '@core/primitives/ssh/api';
import { useMachineStatusKind } from '../use-machine-status-kind';

/** Freeform row content for the Machines CollectionView; the shell owns click handling. */
export const MachineListRow = observer(function MachineListRow({
  machine,
}: {
  machine: SshConfig;
}) {
  const machineStatus = useMachineStatusKind({
    machineId: machine.id,
  });

  return (
    <div className="flex min-w-0 items-center gap-3">
      <MachineStatus status={machineStatus} size="1.25rem" />
      <span className="truncate text-sm text-foreground">{machine.name}</span>
    </div>
  );
});
