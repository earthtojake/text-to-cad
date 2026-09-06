import type { StateInstrumentation } from './node';
import { StateNode, type CommitOptions, type Readable, type Revision } from './node';

export type CellOptions<T> = {
  equals?: (left: T, right: T) => boolean;
  name?: string;
  instrumentation?: StateInstrumentation;
  onObservedChange?: (observed: boolean) => void;
};

export interface Cell<T> extends Readable<T> {
  set(next: T, options?: CommitOptions): Revision;
  update(update: (previous: T) => T, options?: CommitOptions): Revision;
}

class CellNode<T> extends StateNode<T> implements Cell<T> {
  constructor(initial: T, options: CellOptions<T> = {}) {
    super(initial, options);
  }

  set(next: T, options: CommitOptions = {}): Revision {
    return this.commit(next, {
      ...options,
      status: options.status ?? 'live',
    });
  }

  update(update: (previous: T) => T, options: CommitOptions = {}): Revision {
    return this.set(update(this.peek()), options);
  }
}

export function cell<T>(initial: T, options: CellOptions<T> = {}): Cell<T> {
  return new CellNode(initial, options);
}
