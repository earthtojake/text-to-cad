import type { MachineStatusKind } from '@emdash/ui/react/components';
import type { HostAvailabilityState } from '@core/services/hosts/api';

export function deriveMachineStatusKind({
  availability,
}: {
  availability: HostAvailabilityState | undefined;
}): MachineStatusKind {
  if (!availability || availability.kind === 'suspended') return 'idle';
  if (availability.kind === 'preparing') return 'initializing';
  if (availability.kind === 'ready') return 'successful';
  return availability.issue ? 'error' : 'idle';
}
