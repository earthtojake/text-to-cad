import { pokeChannel } from '@emdash/wire/state';
import type { MementoModelKey } from '@core/primitives/mementos/api';

type Match<T> = (payload: T) => boolean;

export type MementoPoke = {
  subjectKind?: string;
  subjectKey?: string;
};

export const mementoPokes = {
  value: pokeChannel<MementoPoke>('mementos:value'),
};

export function matchMementoKey(key: MementoModelKey): Match<MementoPoke> {
  return (payload) =>
    (payload.subjectKind === undefined || payload.subjectKind === key.kind) &&
    (payload.subjectKey === undefined || payload.subjectKey === key.key);
}
