import { reaction } from 'mobx';
import { useCallback, useMemo, useSyncExternalStore } from 'react';
import type { z } from 'zod';
import type { MementoDef } from '@core/primitives/mementos/api';
import type { SubjectDef } from '@core/primitives/subjects/api';
import type { MementoHandle } from '../browser';
import { useSubjectSpace } from './subject-context';

export interface UseMementoControls {
  readonly reset: () => Promise<void>;
}

export type MementoSetter<TValue> = (next: TValue | ((current: TValue) => TValue)) => void;

export function useMemento<TValue, TKind extends string>(
  definition: MementoDef<TValue, SubjectDef<TKind, z.ZodType>>
): readonly [TValue, MementoSetter<TValue>, UseMementoControls] {
  const space = useSubjectSpace(definition.subject);
  const handle = useMemo(() => space.handle(definition), [definition, space]);
  const value = useHandleValue(handle);
  const update = useCallback<MementoSetter<TValue>>((next) => handle.update(next), [handle]);
  const reset = useCallback(async () => await handle.reset(), [handle]);
  const controls = useMemo<UseMementoControls>(() => ({ reset }), [reset]);
  return [value, update, controls] as const;
}

function useHandleValue<TValue>(handle: MementoHandle<TValue>): TValue {
  const subscribe = useCallback(
    (onStoreChange: () => void) =>
      reaction(
        () => handle.value,
        () => onStoreChange()
      ),
    [handle]
  );
  const getSnapshot = useCallback(() => handle.value, [handle]);
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
