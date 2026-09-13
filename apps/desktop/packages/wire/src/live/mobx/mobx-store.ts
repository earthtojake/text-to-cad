import { observable, runInAction, toJS } from 'mobx';
import type { StateStore } from '../../live/replica/store';
import { applyPatches, type Patch } from '../../live/state/immer-setup';

export function createImmutableMobxStore<T>(): StateStore<T> {
  let ready = false;
  const value = observable.box<T | undefined>(undefined, { deep: false });

  return {
    reset(data) {
      runInAction(() => {
        ready = true;
        value.set(structuredClone(data));
      });
    },
    apply(patches) {
      const current = value.get();
      if (!ready) throw new Error('StateStore has not been seeded');
      const next = applyPatches(current as object, patches) as T;
      runInAction(() => value.set(next));
      return next;
    },
    current() {
      const current = value.get();
      if (!ready) throw new Error('StateStore has not been seeded');
      return current as T;
    },
    serialize() {
      const current = value.get();
      if (!ready) throw new Error('StateStore has not been seeded');
      return current as T;
    },
  };
}

export function createReactiveMobxStore<T>(): StateStore<T> {
  let ready = false;
  const value = observable.box<T | undefined>(undefined, { deep: false });

  return {
    reset(data) {
      runInAction(() => {
        ready = true;
        value.set(toObservableData(data));
      });
    },
    apply(patches) {
      if (!ready) throw new Error('StateStore has not been seeded');
      runInAction(() => {
        for (const patch of patches) {
          applyMobxPatch(value, patch);
        }
      });
      return value.get() as T;
    },
    current() {
      const current = value.get();
      if (!ready) throw new Error('StateStore has not been seeded');
      return current as T;
    },
    serialize() {
      const current = value.get();
      if (!ready) throw new Error('StateStore has not been seeded');
      return toJS(current) as T;
    },
  };
}

function applyMobxPatch(root: { get(): unknown; set(value: unknown): void }, patch: Patch): void {
  if (patch.path.length === 0) {
    if (patch.op === 'remove') {
      root.set(undefined);
    } else {
      root.set(toObservableData(patch.value));
    }
    return;
  }

  const parent = parentForPath(root.get(), patch.path);
  const key = patch.path[patch.path.length - 1];
  if (Array.isArray(parent)) {
    const index = key === '-' ? parent.length : Number(key);
    if (patch.op === 'remove') {
      parent.splice(index, 1);
    } else if (patch.op === 'add') {
      parent.splice(index, 0, toObservableData(patch.value));
    } else {
      parent[index] = toObservableData(patch.value);
    }
    return;
  }

  if (!isObject(parent)) {
    throw new Error(`Cannot apply patch to non-object parent at ${patch.path.join('.')}`);
  }

  if (patch.op === 'remove') {
    delete (parent as Record<PropertyKey, unknown>)[key];
  } else {
    (parent as Record<PropertyKey, unknown>)[key] = toObservableData(patch.value);
  }
}

function parentForPath(root: unknown, path: Patch['path']): unknown {
  let node = root;
  for (const segment of path.slice(0, -1)) {
    if (!isObject(node)) throw new Error(`Cannot traverse non-object patch path ${path.join('.')}`);
    node = (node as Record<PropertyKey, unknown>)[segment];
  }
  return node;
}

function toObservableData<T>(data: T): T {
  const cloned = structuredClone(data);
  return isObject(cloned) ? (observable(cloned) as T) : cloned;
}

function isObject(value: unknown): value is object {
  return typeof value === 'object' && value !== null;
}
