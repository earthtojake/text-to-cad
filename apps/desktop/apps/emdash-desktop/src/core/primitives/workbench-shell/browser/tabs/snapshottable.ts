export interface Snapshottable<T> {
  readonly snapshot: T;
  restoreSnapshot: (snapshot: Partial<T>) => void;
  initializeDefault?: () => void;
}
