import type { ProjectHostAccessState } from './stores/project-context';

export type LiveRuntimeObservation<T> =
  | { kind: 'live'; value: T }
  | { kind: 'stale'; value: T }
  | { kind: 'unavailable' };

export function classifyLiveRuntimeObservation<T>(
  access: ProjectHostAccessState,
  observed: T | undefined
): LiveRuntimeObservation<T> {
  if (access.kind === 'ready') {
    return observed === undefined ? { kind: 'unavailable' } : { kind: 'live', value: observed };
  }
  return observed === undefined ? { kind: 'unavailable' } : { kind: 'stale', value: observed };
}
