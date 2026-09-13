export type HostObservation<T> =
  | { kind: 'never-observed' }
  | { kind: 'observed'; value: T; observedAt: number };

export type ProjectHostObservation<T> =
  | { kind: 'fresh'; value: T; observedAt: number }
  | { kind: 'stale'; value: T; observedAt: number }
  | { kind: 'unavailable' };
