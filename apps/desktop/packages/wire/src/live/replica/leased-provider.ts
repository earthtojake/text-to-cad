import type { PendingLease } from '@emdash/shared';
import type { LiveMutationResult, LiveSource } from '../../api/channel';
import type {
  LiveModelKey,
  LiveModelMutations,
  LiveModelDef,
  LiveModelStates,
  MutationData,
  MutationError,
} from '../../api/define';
import type { LiveModelMutationEnvelope } from './provider';

export type LeasedLiveModelProvider<Group extends LiveModelDef = LiveModelDef> = {
  readonly kind: 'leasedLiveModelProvider';
  readonly contract: Group;
  acquireState<Name extends Extract<keyof LiveModelStates<Group>, string>>(
    key: LiveModelKey<Group>,
    name: Name
  ): PendingLease<LiveSource>;
  runMutation<Name extends Extract<keyof LiveModelMutations<Group>, string>>(
    name: Name,
    envelope: LiveModelMutationEnvelope<Group, Name>
  ): Promise<
    LiveMutationResult<
      MutationData<LiveModelMutations<Group>[Name]>,
      MutationError<LiveModelMutations<Group>[Name]>
    >
  >;
  dispose(): Promise<void>;
};

export function isLeasedLiveModelProvider(value: unknown): value is LeasedLiveModelProvider {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { kind?: unknown }).kind === 'leasedLiveModelProvider'
  );
}
