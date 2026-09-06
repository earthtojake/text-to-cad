import { keyValueIoError, type KeyValueStore } from '@emdash/core/primitives/kv/api';
import { ok, type Serializable } from '@emdash/shared';
import { eq, like } from 'drizzle-orm';
import { kv } from '@core/services/app-db/node/schema';
import { log } from '@main/lib/logger';
import { getAppDb } from './instance';

export const desktopKeyValueStore: KeyValueStore = {
  async get(key) {
    try {
      const rows = await getAppDb()
        .select({ value: kv.value })
        .from(kv)
        .where(eq(kv.key, key))
        .limit(1);
      const raw = rows[0]?.value;
      if (raw === undefined || raw === null) return ok(null);
      return ok(JSON.parse(raw) as Serializable);
    } catch (error) {
      return { success: false, error: keyValueIoError(error, 'Failed to read KV entry', key) };
    }
  },

  async set(key, value) {
    try {
      const serialised = JSON.stringify(value);
      const now = Date.now();
      await getAppDb()
        .insert(kv)
        .values({ key, value: serialised, updatedAt: now })
        .onConflictDoUpdate({ target: kv.key, set: { value: serialised, updatedAt: now } });
      return ok();
    } catch (error) {
      return { success: false, error: keyValueIoError(error, 'Failed to write KV entry', key) };
    }
  },

  async delete(key) {
    try {
      await getAppDb().delete(kv).where(eq(kv.key, key));
      return ok();
    } catch (error) {
      return { success: false, error: keyValueIoError(error, 'Failed to delete KV entry', key) };
    }
  },

  async getAll() {
    try {
      const rows = await getAppDb().select().from(kv);
      const result: Record<string, Serializable> = {};
      for (const row of rows) {
        try {
          result[row.key] = JSON.parse(row.value) as Serializable;
        } catch {
          // Skip malformed legacy entries.
        }
      }
      return ok(result);
    } catch (error) {
      return { success: false, error: keyValueIoError(error, 'Failed to list KV entries') };
    }
  },
};

export class KV<TSchema extends Record<string, unknown>> {
  constructor(private readonly namespace: string) {}

  private prefixed(key: string): string {
    return `${this.namespace}:${key}`;
  }

  async get<K extends keyof TSchema & string>(key: K): Promise<TSchema[K] | null> {
    const result = await desktopKeyValueStore.get(this.prefixed(key));
    return result.success ? (result.data as TSchema[K] | null) : null;
  }

  async set<K extends keyof TSchema & string>(key: K, value: TSchema[K]): Promise<void> {
    try {
      await this.write(key, value);
    } catch (e) {
      log.error('Failed to set KV', { key, value, error: e });
    }
  }

  async setOrThrow<K extends keyof TSchema & string>(key: K, value: TSchema[K]): Promise<void> {
    await this.write(key, value);
  }

  async del<K extends keyof TSchema & string>(key: K): Promise<void> {
    try {
      const result = await desktopKeyValueStore.delete(this.prefixed(key));
      if (!result.success) throw new Error(result.error.message);
    } catch (e) {
      log.error('Failed to delete KV', { key, error: e });
    }
  }

  async clear(): Promise<void> {
    try {
      await getAppDb()
        .delete(kv)
        .where(like(kv.key, `${this.namespace}:%`));
    } catch (e) {
      log.error('Failed to clear KV', { namespace: this.namespace, error: e });
    }
  }

  async getAll(): Promise<Partial<TSchema>> {
    const rows = await getAppDb()
      .select()
      .from(kv)
      .where(like(kv.key, `${this.namespace}:%`));
    const result: Record<string, unknown> = {};
    for (const row of rows) {
      const shortKey = row.key.slice(this.namespace.length + 1);
      try {
        result[shortKey] = JSON.parse(row.value);
      } catch {
        // skip malformed entries
      }
    }
    return result as Partial<TSchema>;
  }

  private async write<K extends keyof TSchema & string>(key: K, value: TSchema[K]): Promise<void> {
    const result = await desktopKeyValueStore.set(this.prefixed(key), value as Serializable);
    if (!result.success) throw new Error(result.error.message);
  }
}
