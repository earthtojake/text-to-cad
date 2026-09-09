import type { HostRef } from '@emdash/core/primitives/host/api';

type SweepTriggerListener = (host: HostRef) => void;

export type ReconcileSweepTriggers = {
  poke(host: HostRef): void;
  subscribe(listener: SweepTriggerListener): () => void;
};

/**
 * In-process trigger channel for the reconcile sweep (ADR 0006): the tombstone write
 * path pokes it so an entity tombstoned while its host is (or flaps back) reachable
 * sweeps immediately instead of waiting for the backstop.
 */
export function createReconcileSweepTriggers(): ReconcileSweepTriggers {
  const listeners = new Set<SweepTriggerListener>();
  return {
    poke(host) {
      for (const listener of [...listeners]) listener(host);
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

let installed: ReconcileSweepTriggers | undefined;

/**
 * Installs the channel the boot composition root constructed (main-patterns: Core
 * modules export factories, not constructed instances; boot owns construction).
 */
export function installReconcileSweepTriggers(triggers: ReconcileSweepTriggers): void {
  installed = triggers;
}

/**
 * Instance bridge for free-function write paths (tombstone writers), module-level
 * like `appDbPokes` so they never thread the sweep service through their callers.
 * Delegates to the boot-installed channel; a lazy default keeps tests that exercise
 * write paths without a boot working unchanged.
 */
export const reconcileSweepTriggers: ReconcileSweepTriggers = {
  poke(host) {
    instance().poke(host);
  },
  subscribe(listener) {
    return instance().subscribe(listener);
  },
};

function instance(): ReconcileSweepTriggers {
  installed ??= createReconcileSweepTriggers();
  return installed;
}
