import type { StateNode } from './node';

/**
 * Internal wiring for observation-based retention: nodes constructed while a
 * registrar is active (a family factory run) are reported to it, and the
 * registrar can attach observed-change listeners without touching the node's
 * own `onObservedChange` option. Not part of the public state surface.
 */
type ObservedChangeListener = (observed: boolean) => void;

let currentRegistrar: ((node: StateNode<unknown>) => void) | undefined;
const listeners = new WeakMap<StateNode<unknown>, Set<ObservedChangeListener>>();

export function withObservationRegistrar<T>(
  registrar: (node: StateNode<unknown>) => void,
  work: () => T
): T {
  const previous = currentRegistrar;
  currentRegistrar = registrar;
  try {
    return work();
  } finally {
    currentRegistrar = previous;
  }
}

export function nodeConstructed(node: StateNode<unknown>): void {
  currentRegistrar?.(node);
}

export function addObservedChangeListener(
  node: StateNode<unknown>,
  listener: ObservedChangeListener
): void {
  let set = listeners.get(node);
  if (!set) {
    set = new Set();
    listeners.set(node, set);
  }
  set.add(listener);
}

export function notifyObservedChange(node: StateNode<unknown>, observed: boolean): void {
  const set = listeners.get(node);
  if (!set) return;
  for (const listener of [...set]) listener(observed);
}
