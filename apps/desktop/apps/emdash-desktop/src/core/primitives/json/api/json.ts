export type JsonPrimitive = boolean | number | string | null;

export type JsonValue =
  | JsonPrimitive
  | { readonly [key: string]: JsonValue | undefined }
  | readonly JsonValue[];

export type JsonObject = { readonly [key: string]: JsonValue | undefined };

export function deepFreeze<T extends JsonValue>(value: T): T {
  if (value === null || typeof value !== 'object' || Object.isFrozen(value)) {
    return value;
  }

  Object.freeze(value);
  for (const nested of Object.values(value)) {
    if (nested !== undefined) {
      deepFreeze(nested);
    }
  }
  return value;
}
