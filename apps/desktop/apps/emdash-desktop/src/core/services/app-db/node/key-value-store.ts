import type { Serializable } from '@emdash/shared';
import { eq, like } from 'drizzle-orm';
import type { AppDb } from './db';
import { kv } from './schema';

type KeyValueLogger = {
  error(message: string, context: Record<string, unknown>): void;
};

export class AppDbKeyValueStore<TSchema extends Record<string, unknown>> {
  constructor(
    private readonly db: AppDb,
    private readonly namespace: string,
    private readonly logger?: KeyValueLogger
  ) {}

  private prefixed(key: string): string {
    return `${this.namespace}:${key}`;
  }

  async get<K extends keyof TSchema & string>(key: K): Promise<TSchema[K] | null> {
    try {
      const [row] = await this.db
        .select({ value: kv.value })
        .from(kv)
        .where(eq(kv.key, this.prefixed(key)))
        .limit(1);
      if (row?.value === undefined || row.value === null) return null;
      return JSON.parse(row.value) as TSchema[K];
    } catch (error) {
      this.logger?.error('Failed to read KV', { key, error });
      return null;
    }
  }

  async set<K extends keyof TSchema & string>(key: K, value: TSchema[K]): Promise<void> {
    try {
      await this.write(key, value);
    } catch (error) {
      this.logger?.error('Failed to set KV', { key, value, error });
    }
  }

  async setOrThrow<K extends keyof TSchema & string>(key: K, value: TSchema[K]): Promise<void> {
    await this.write(key, value);
  }

  async del<K extends keyof TSchema & string>(key: K): Promise<void> {
    try {
      await this.db.delete(kv).where(eq(kv.key, this.prefixed(key)));
    } catch (error) {
      this.logger?.error('Failed to delete KV', { key, error });
    }
  }

  async clear(): Promise<void> {
    try {
      await this.db.delete(kv).where(like(kv.key, `${this.namespace}:%`));
    } catch (error) {
      this.logger?.error('Failed to clear KV', { namespace: this.namespace, error });
    }
  }

  async getAll(): Promise<Partial<TSchema>> {
    const rows = await this.db
      .select()
      .from(kv)
      .where(like(kv.key, `${this.namespace}:%`));
    const result: Record<string, Serializable> = {};
    for (const row of rows) {
      const shortKey = row.key.slice(this.namespace.length + 1);
      try {
        result[shortKey] = JSON.parse(row.value) as Serializable;
      } catch {
        // Skip malformed legacy entries.
      }
    }
    return result as Partial<TSchema>;
  }

  private async write<K extends keyof TSchema & string>(key: K, value: TSchema[K]): Promise<void> {
    const prefixedKey = this.prefixed(key);
    const serialised = JSON.stringify(value);
    const now = Date.now();
    await this.db
      .insert(kv)
      .values({ key: prefixedKey, value: serialised, updatedAt: now })
      .onConflictDoUpdate({ target: kv.key, set: { value: serialised, updatedAt: now } });
  }
}
