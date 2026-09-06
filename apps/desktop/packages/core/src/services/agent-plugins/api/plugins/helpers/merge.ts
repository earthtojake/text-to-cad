/**
 * Shallow merge — override wins for every key present in override.
 */
export function mergeOverride<T>(base: T, override: Partial<T>): T {
  return { ...base, ...override };
}

/**
 * Deep recursive merge — plain objects are merged recursively,
 * everything else (arrays, primitives) is replaced by override.
 */
export function mergeDeep<T extends Record<string, unknown>>(base: T, override: Partial<T>): T {
  const result: Record<string, unknown> = { ...base };
  for (const key of Object.keys(override) as (keyof T)[]) {
    const overrideVal = override[key];
    const baseVal = base[key];
    if (
      overrideVal !== null &&
      typeof overrideVal === 'object' &&
      !Array.isArray(overrideVal) &&
      baseVal !== null &&
      typeof baseVal === 'object' &&
      !Array.isArray(baseVal)
    ) {
      result[key as string] = mergeDeep(
        baseVal as Record<string, unknown>,
        overrideVal as Partial<Record<string, unknown>>
      );
    } else if (overrideVal !== undefined) {
      result[key as string] = overrideVal;
    }
  }
  return result as T;
}

/**
 * Deep merge where array values are concatenated rather than replaced.
 * Objects are still merged recursively; the override's arrays are appended
 * to the base's arrays (duplicates are preserved).
 */
export function mergeConcatArrays<T extends Record<string, unknown>>(
  base: T,
  override: Partial<T>
): T {
  const result: Record<string, unknown> = { ...base };
  for (const key of Object.keys(override) as (keyof T)[]) {
    const overrideVal = override[key];
    const baseVal = base[key];
    if (overrideVal === undefined) continue;
    if (Array.isArray(overrideVal) && Array.isArray(baseVal)) {
      result[key as string] = [...baseVal, ...overrideVal];
    } else if (
      overrideVal !== null &&
      typeof overrideVal === 'object' &&
      !Array.isArray(overrideVal) &&
      baseVal !== null &&
      typeof baseVal === 'object' &&
      !Array.isArray(baseVal)
    ) {
      result[key as string] = mergeConcatArrays(
        baseVal as Record<string, unknown>,
        overrideVal as Partial<Record<string, unknown>>
      );
    } else {
      result[key as string] = overrideVal;
    }
  }
  return result as T;
}
