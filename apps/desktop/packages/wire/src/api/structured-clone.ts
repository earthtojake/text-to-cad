export type StructuredCloneFailure = {
  path: string;
  reason: string;
};

/**
 * Identifies errors raised when a transport cannot structured-clone a message.
 *
 * The name check intentionally avoids `instanceof DOMException` because errors
 * can cross realms in Electron.
 */
export function isStructuredCloneError(error: unknown): boolean {
  return (
    typeof error === 'object' &&
    error !== null &&
    (error as { name?: unknown }).name === 'DataCloneError'
  );
}

/**
 * Finds the deepest value that fails the structured-clone algorithm.
 *
 * This is intended for failure diagnostics, not eager validation. It invokes
 * `structuredClone` while walking the value and may therefore be relatively
 * expensive for large payloads.
 */
export function findStructuredCloneFailure(
  value: unknown,
  rootPath = 'value'
): StructuredCloneFailure | null {
  if (canStructuredClone(value)) return null;
  return inspectFailure(value, rootPath, new WeakSet<object>());
}

export function formatStructuredCloneFailure(value: unknown, rootPath = 'value'): string {
  const failure = findStructuredCloneFailure(value, rootPath);
  if (!failure) return `'${rootPath}' could not be structured-cloned`;
  return `'${failure.path}' ${failure.reason}`;
}

function inspectFailure(
  value: unknown,
  path: string,
  seen: WeakSet<object>
): StructuredCloneFailure {
  if (typeof value === 'function') {
    return { path, reason: 'is a function, which cannot be structured-cloned' };
  }
  if (typeof value === 'symbol') {
    return { path, reason: 'is a symbol, which cannot be structured-cloned' };
  }
  if (typeof value !== 'object' || value === null) {
    return { path, reason: 'could not be structured-cloned' };
  }
  if (seen.has(value)) {
    return { path, reason: 'is part of a value that could not be structured-cloned' };
  }
  seen.add(value);

  if (value instanceof Map) {
    let index = 0;
    for (const [key, entryValue] of value) {
      const keyPath = `${path}.<key:${index}>`;
      if (!canStructuredClone(key)) return inspectFailure(key, keyPath, seen);
      const valuePath = `${path}.<value:${index}>`;
      if (!canStructuredClone(entryValue)) return inspectFailure(entryValue, valuePath, seen);
      index += 1;
    }
  } else if (value instanceof Set) {
    let index = 0;
    for (const entry of value) {
      const entryPath = `${path}.<value:${index}>`;
      if (!canStructuredClone(entry)) return inspectFailure(entry, entryPath, seen);
      index += 1;
    }
  } else {
    try {
      for (const [key, child] of Object.entries(value)) {
        if (!canStructuredClone(child)) {
          return inspectFailure(child, appendPath(path, key, Array.isArray(value)), seen);
        }
      }
    } catch {
      return {
        path,
        reason: 'could not be inspected after structured cloning failed',
      };
    }
  }

  const kind = describeValueKind(value);
  const article = /^[AEIOU]/i.test(kind) ? 'an' : 'a';
  return {
    path,
    reason: `is ${article} ${kind} value that cannot be structured-cloned (it may be Proxy-backed)`,
  };
}

function canStructuredClone(value: unknown): boolean {
  try {
    structuredClone(value);
    return true;
  } catch {
    return false;
  }
}

function appendPath(path: string, key: string, parentIsArray: boolean): string {
  if (parentIsArray && /^\d+$/.test(key)) return `${path}[${key}]`;
  if (/^[A-Za-z_$][\w$]*$/.test(key)) return `${path}.${key}`;
  return `${path}[${JSON.stringify(key)}]`;
}

function describeValueKind(value: object): string {
  if (Array.isArray(value)) return 'Array';
  try {
    const constructorName = value.constructor?.name;
    if (constructorName) return constructorName;
  } catch {
    // Proxy traps can make constructor access fail.
  }
  return 'non-plain object';
}
