import { log } from '@emdash/shared/logger';

export function parseJsonObject(raw: string): unknown {
  const parsed = JSON.parse(raw);
  return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
}

export function compactUndefined<T extends Record<string, unknown>>(obj: T): Partial<T> {
  const next: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (value === undefined) continue;
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const child = compactUndefined(value as Record<string, unknown>);
      if (Object.keys(child).length > 0) next[key] = child;
      continue;
    }
    next[key] = value;
  }
  return next as Partial<T>;
}

export function readJson<T>(raw: string, schema: { parse(value: unknown): T }, source: string): T {
  try {
    return schema.parse(parseJsonObject(raw));
  } catch (error) {
    log.warn(`Failed to parse ${source}, using empty settings`, { error });
    return schema.parse({});
  }
}
