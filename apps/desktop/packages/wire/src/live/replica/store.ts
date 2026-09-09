import type { z } from 'zod';
import type { LiveSnapshot, LiveUpdate } from '../../api/channel';
import type { LiveFollowerApplyResult, LiveMaterializer } from '../follower';
import { applyPatches, type Patch } from '../state/immer-setup';

export interface StateStore<T> {
  reset(data: T): void;
  apply(patches: Patch[]): T;
  current(): T;
  serialize(): T;
}

export function createPlainStore<T>(): StateStore<T> {
  let ready = false;
  let value: T | undefined;

  return {
    reset(data) {
      ready = true;
      value = structuredClone(data);
    },
    apply(patches) {
      if (!ready) throw new Error('StateStore has not been seeded');
      value = applyPatches(value as object, patches) as T;
      return value;
    },
    current() {
      if (!ready) throw new Error('StateStore has not been seeded');
      return value as T;
    },
    serialize() {
      if (!ready) throw new Error('StateStore has not been seeded');
      return value as T;
    },
  };
}

export function createStateMaterializer<T>(
  store: StateStore<T>,
  schema?: z.ZodType<T>
): LiveMaterializer<T> {
  return {
    seed(snapshot: LiveSnapshot<T>) {
      store.reset(snapshot.data);
    },
    apply(update: LiveUpdate): LiveFollowerApplyResult {
      try {
        store.apply(update.delta as Patch[]);
        if (!schema || readNodeEnv() === 'production') return { ok: true };
        const parsed = schema.safeParse(store.serialize());
        return parsed.success
          ? { ok: true }
          : { ok: false, reason: 'validation', details: { error: parsed.error } };
      } catch (error) {
        return { ok: false, reason: 'patch-failed', details: { error } };
      }
    },
  };
}

// Structural declaration keeps this browser-reachable file free of node
// ambient types; the typeof guard already handles environments without it.
declare const process: { env: Record<string, string | undefined> } | undefined;

function readNodeEnv(): string | undefined {
  return typeof process !== 'undefined' ? process.env['NODE_ENV'] : undefined;
}
