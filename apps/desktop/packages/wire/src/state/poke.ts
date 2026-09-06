import type { Unsubscribe } from '@emdash/shared';

export type PokeSubscription = {
  subscribe(listener: () => void): Unsubscribe;
};

export type PokeChannel<T = void> = {
  readonly name: string;
  poke: undefined extends T ? (payload?: T) => void : (payload: T) => void;
  subscription(match?: (payload: T) => boolean): PokeSubscription;
};

export function pokeChannel<T = void>(name: string): PokeChannel<T> {
  const listeners = new Set<(payload: T) => void>();
  return {
    name,
    poke(payload?: T) {
      for (const listener of [...listeners]) listener(payload as T);
    },
    subscription(match) {
      return {
        subscribe(listener) {
          const wrapped = (payload: T): void => {
            if (!match || match(payload)) listener();
          };
          listeners.add(wrapped);
          return () => listeners.delete(wrapped);
        },
      };
    },
  } as PokeChannel<T>;
}
