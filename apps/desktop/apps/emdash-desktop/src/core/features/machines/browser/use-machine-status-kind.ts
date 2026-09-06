import { hostRef } from '@emdash/core/primitives/host/api';
import type { MachineStatusKind } from '@emdash/ui/react/components';
import { remote, type RemoteModel } from '@emdash/wire/state';
import { useRemoteModelState } from '@core/primitives/wire/browser/use-remote-model-state';
import { hostsContract, type HostAvailabilityState } from '@core/services/hosts/api';
import { getHostsClient } from '@core/services/hosts/api/client';
import { deriveMachineStatusKind } from './components/machine-status-kind';

let availabilityRemotePromise: Promise<RemoteModel<typeof hostsContract.availability>> | undefined;

export function useMachineStatusKind({
  machineId,
}: {
  machineId: string | undefined;
}): MachineStatusKind {
  const availability = useMachineAvailability(machineId);
  return deriveMachineStatusKind({ availability });
}

export function useMachineAvailability(
  machineId: string | undefined
): HostAvailabilityState | undefined {
  const availability = useRemoteModelState(
    hostsContract.availability,
    getAvailabilityRemote,
    { host: hostRef('remote', machineId ?? 'unselected') },
    'state',
    { enabled: machineId !== undefined }
  );

  return availability.value;
}

function getAvailabilityRemote(): Promise<RemoteModel<typeof hostsContract.availability>> {
  availabilityRemotePromise ??= getHostsClient().then((client) =>
    remote(hostsContract.availability, client.availability, {
      lingerMs: 15_000,
    })
  );
  return availabilityRemotePromise;
}

export async function resetMachineAvailabilityForTests(): Promise<void> {
  const remoteModel = await availabilityRemotePromise;
  availabilityRemotePromise = undefined;
  await remoteModel?.dispose();
}
