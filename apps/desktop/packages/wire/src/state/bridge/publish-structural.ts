import type { CommitOptions, Revision } from '../core';
import { peek, revisionOf, type Cell } from '../core';
import { produce } from '../live-immer';
import { assignDraft } from './assign-draft';

export function publishStructural<T>(
  target: Cell<T>,
  next: T,
  options: CommitOptions = {}
): Revision {
  const current = peek(target);
  if (Object.is(current, next)) return revisionOf(target);

  const updated = produce(current, (draft) => {
    const replacement = assignDraft(draft as T, next);
    if (replacement !== undefined) return replacement as never;
  }) as T;
  if (Object.is(current, updated)) return revisionOf(target);
  return target.set(updated, options);
}
