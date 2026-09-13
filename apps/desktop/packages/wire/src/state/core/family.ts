import type { Scope } from '@emdash/shared/concurrency';
import type { Clock } from '@emdash/shared/scheduling';
import { keyedRetention, type RetainedEntry } from './keyed-retention';
import type { StateNode } from './node';
import { addObservedChangeListener, withObservationRegistrar } from './observed-registry';

export type FamilyOptions<K> = {
  key?: (key: K) => string;
  lingerMs?: number;
  name?: string;
  scope?: Scope;
  clock?: Clock;
};

export type Family<K, R> = {
  (key: K): R;
  peekMember(key: K): R | undefined;
  retain(key: K): () => void;
  dispose(): Promise<void>;
};

export function family<K, R>(
  factory: (key: K, scope: Scope) => R,
  options: FamilyOptions<K> = {}
): Family<K, R> {
  const members = keyedRetention<K, R>({
    key: options.key,
    lingerMs: options.lingerMs ?? 15_000,
    name: options.name ?? 'state-family',
    scope: options.scope,
    clock: options.clock,
    create: (key, scope, entry) => {
      // Observation ⇒ retention: every state node created by the factory keeps
      // the member retained while it has at least one observer. The linger
      // window starts when the last observer detaches.
      const nodes: StateNode<unknown>[] = [];
      const value = withObservationRegistrar(
        (node) => nodes.push(node),
        () => factory(key, scope)
      );
      for (const node of nodes) attachObservedRetention(node, entry);
      return value;
    },
  });

  const get = ((key: K): R => {
    assertActive();
    return members.ensure(key).value;
  }) as Family<K, R>;

  get.peekMember = (key) => members.peek(key)?.value;
  get.retain = (key) => {
    assertActive();
    return members.retain(key);
  };
  get.dispose = () => members.dispose();

  return get;

  function attachObservedRetention(node: StateNode<unknown>, entry: RetainedEntry<K, R>): void {
    let release: (() => void) | undefined;
    addObservedChangeListener(node, (observed) => {
      if (observed) {
        release ??= members.retainEntry(entry);
      } else {
        release?.();
        release = undefined;
      }
    });
  }

  function assertActive(): void {
    if (members.disposed) throw new Error('State family is disposed');
  }
}
