export function assignDraft<T>(draft: T, next: T): T | void {
  if (!isObjectLike(draft) || !isObjectLike(next)) return structuredClone(next);
  if (Array.isArray(draft) || Array.isArray(next)) {
    if (!Array.isArray(draft) || !Array.isArray(next)) return structuredClone(next);
    draft.length = next.length;
    for (let index = 0; index < next.length; index += 1) {
      const replacement = assignDraftValue(draft[index], next[index]);
      if (replacement !== undefined) draft[index] = replacement;
    }
    return;
  }

  const draftRecord = draft as Record<string, unknown>;
  const nextRecord = next as Record<string, unknown>;
  for (const key of Object.keys(draftRecord)) {
    if (!(key in nextRecord)) delete draftRecord[key];
  }
  for (const [key, incoming] of Object.entries(nextRecord)) {
    const replacement = assignDraftValue(draftRecord[key], incoming);
    if (replacement !== undefined) draftRecord[key] = replacement;
  }
}

function assignDraftValue(current: unknown, incoming: unknown): unknown | undefined {
  if (Object.is(current, incoming)) return undefined;
  if (isObjectLike(current) && isObjectLike(incoming)) {
    const replacement = assignDraft(current, incoming);
    return replacement === undefined ? undefined : replacement;
  }
  return incoming;
}

function isObjectLike(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
