import { createScope } from '@emdash/shared/concurrency';
import { stableStringify } from '@emdash/shared/util';
import {
  type LiveModelDef,
  type LiveModelKey,
  type LiveModelStates,
  type LiveStateData,
} from '@emdash/wire/rpc';
import { observe, type RemoteModel, type Snapshot, type StateStatus } from '@emdash/wire/state';
import { useEffect, useRef, useState } from 'react';

type StateName<Group extends LiveModelDef> = Extract<keyof LiveModelStates<Group>, string>;
type StateValue<Group extends LiveModelDef, Name extends StateName<Group>> = LiveStateData<
  LiveModelStates<Group>[Name]
>;

export type UseRemoteModelStateResult<T> = {
  readonly value: T | undefined;
  readonly snapshot: Snapshot<T | undefined> | undefined;
  readonly status: StateStatus;
  readonly ready: boolean;
  readonly isLoading: boolean;
  readonly error: unknown;
  refresh(): Promise<void>;
};

export type UseRemoteModelStateOptions<T> = {
  readonly enabled?: boolean;
  readonly initialValue?: T;
};

export function useRemoteModelState<Group extends LiveModelDef, Name extends StateName<Group>>(
  contract: Group,
  getRemote: () => Promise<RemoteModel<Group>>,
  key: LiveModelKey<Group>,
  stateName: Name,
  options: UseRemoteModelStateOptions<StateValue<Group, Name>> = {}
): UseRemoteModelStateResult<StateValue<Group, Name>> {
  const initialValueRef = useRef(options.initialValue);
  const getRemoteRef = useRef(getRemote);
  const keyRef = useRef(key);
  const keyId = stableStringify(key);
  getRemoteRef.current = getRemote;
  keyRef.current = key;

  const [state, setState] = useState<UseRemoteModelStateResult<StateValue<Group, Name>>>(() =>
    loadingState(initialValueRef.current)
  );
  const enabled = options.enabled ?? true;

  useEffect(() => {
    if (!enabled) {
      setState(loadingState(initialValueRef.current));
      return;
    }

    const scope = createScope({ label: `remote-model-state:${contract.id}.${String(stateName)}` });
    let disposed = false;
    setState((current) => ({
      ...current,
      status: 'loading',
      ready: false,
      isLoading: true,
      error: undefined,
    }));

    void getRemoteRef
      .current()
      .then((remoteModel) => {
        if (disposed) return;
        const member = remoteModel(keyRef.current);
        const remoteState = member.states[stateName];
        observe(
          remoteState,
          (snapshot) => {
            if (disposed) return;
            setState({
              value: snapshot.value as StateValue<Group, Name> | undefined,
              snapshot: snapshot as Snapshot<StateValue<Group, Name> | undefined>,
              status: snapshot.status,
              ready: snapshot.status !== 'loading',
              isLoading: snapshot.status === 'loading',
              error: snapshot.error,
              refresh: () => remoteState.refresh(),
            });
          },
          { scope }
        );
      })
      .catch((error: unknown) => {
        if (disposed) return;
        setState({
          value: initialValueRef.current,
          snapshot: undefined,
          status: 'error',
          ready: true,
          isLoading: false,
          error,
          refresh: async () => {},
        });
      });

    return () => {
      disposed = true;
      void scope.dispose();
    };
  }, [contract.id, enabled, keyId, stateName]);

  return state;
}

function loadingState<T>(initialValue: T | undefined): UseRemoteModelStateResult<T> {
  return {
    value: initialValue,
    snapshot: undefined,
    status: 'loading',
    ready: false,
    isLoading: true,
    error: undefined,
    refresh: async () => {},
  };
}
