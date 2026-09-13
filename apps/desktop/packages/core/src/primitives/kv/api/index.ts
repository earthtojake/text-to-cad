import { err, ok, type Result, type Serializable, toSerializedError } from '@emdash/shared';
import { z } from 'zod';

export type KeyValueStoreError =
  | { type: 'io'; key?: string; message: string; cause?: ReturnType<typeof toSerializedError> }
  | { type: 'decode'; key: string; message: string };

export type KeyValueStore = {
  get(key: string): Promise<Result<Serializable | null, KeyValueStoreError>>;
  set(key: string, value: Serializable): Promise<Result<void, KeyValueStoreError>>;
  delete(key: string): Promise<Result<void, KeyValueStoreError>>;
  getAll(): Promise<Result<Record<string, Serializable>, KeyValueStoreError>>;
};

export type TypedKeyValueNamespace<TSchema extends Record<string, unknown>> = {
  get<K extends keyof TSchema & string>(
    key: K
  ): Promise<Result<TSchema[K] | null, KeyValueStoreError>>;
  set<K extends keyof TSchema & string>(
    key: K,
    value: TSchema[K]
  ): Promise<Result<void, KeyValueStoreError>>;
  delete<K extends keyof TSchema & string>(key: K): Promise<Result<void, KeyValueStoreError>>;
  getAll(): Promise<Result<Partial<TSchema>, KeyValueStoreError>>;
};

export function typedNamespace<TSchema extends Record<string, unknown>>(
  store: KeyValueStore,
  namespace: string,
  schemas: { [K in keyof TSchema & string]: z.ZodType<TSchema[K]> }
): TypedKeyValueNamespace<TSchema> {
  const prefixed = (key: string) => `${namespace}:${key}`;

  return {
    async get(key) {
      const raw = await store.get(prefixed(key));
      if (!raw.success || raw.data === null)
        return raw as Result<TSchema[typeof key] | null, KeyValueStoreError>;
      const parsed = schemas[key].safeParse(raw.data);
      if (!parsed.success) {
        return err({
          type: 'decode',
          key: prefixed(key),
          message: z.prettifyError(parsed.error),
        });
      }
      return ok(parsed.data);
    },

    set(key, value) {
      return store.set(prefixed(key), value as Serializable);
    },

    delete(key) {
      return store.delete(prefixed(key));
    },

    async getAll() {
      const all = await store.getAll();
      if (!all.success) return all as Result<Partial<TSchema>, KeyValueStoreError>;
      const result: Partial<TSchema> = {};
      for (const [rawKey, value] of Object.entries(all.data)) {
        if (!rawKey.startsWith(`${namespace}:`)) continue;
        const key = rawKey.slice(namespace.length + 1) as keyof TSchema & string;
        const schema = schemas[key];
        if (!schema) continue;
        const parsed = schema.safeParse(value);
        if (!parsed.success) continue;
        result[key] = parsed.data;
      }
      return ok(result);
    },
  };
}

export function createMemoryKeyValueStore(
  initial: Record<string, Serializable> = {}
): KeyValueStore {
  const values = new Map<string, Serializable>(Object.entries(initial));
  return {
    async get(key) {
      return ok(values.get(key) ?? null);
    },
    async set(key, value) {
      values.set(key, value);
      return ok();
    },
    async delete(key) {
      values.delete(key);
      return ok();
    },
    async getAll() {
      return ok(Object.fromEntries(values.entries()));
    },
  };
}

export function keyValueIoError(error: unknown, message: string, key?: string): KeyValueStoreError {
  return { type: 'io', key, message, cause: toSerializedError(error) };
}
