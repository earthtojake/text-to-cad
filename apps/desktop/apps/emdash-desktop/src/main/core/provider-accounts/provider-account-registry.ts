import { randomUUID } from 'node:crypto';
import { and, asc, eq, sql } from 'drizzle-orm';
import type { ProviderAccountMeta } from '@core/primitives/provider-accounts/api';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import { providerAccounts, type ProviderAccountRow } from '@core/services/app-db/node/schema';
import { getAppDb } from '@main/db/instance';

/** Meta payload without the schema version field, which the registry supplies. */
export type ProviderAccountMetaInput = Omit<ProviderAccountMeta, 'version'>;

export type ProviderAccount = {
  providerId: string;
  accountId: string;
  credentialRef: string;
  isDefault: boolean;
  meta: ProviderAccountMeta | null;
  createdAt: number;
  updatedAt: number;
};

export type ProviderAccountUpsert = {
  providerId: string;
  accountId: string;
  /**
   * Secret material to store at the account's credentialRef. Omit to leave the
   * stored secret untouched (metadata-only update).
   */
  secret?: string;
  /** Replaces the stored meta when provided; omitted meta keeps the existing value. */
  meta?: ProviderAccountMetaInput;
  /**
   * Secret key override for accounts whose secret already lives at a released
   * key (e.g. GitHub's `github-account-token:<id>`). Ignored when the account
   * already exists — an account's credentialRef never changes.
   */
  credentialRef?: string;
};

export type ProviderAccountUpsertResult = {
  account: ProviderAccount;
  status: 'created' | 'updated';
};

export type ProviderAccountSecretStore = {
  getSecret(key: string): Promise<string | null>;
  setSecret(key: string, value: string): Promise<void>;
  deleteSecret(key: string): Promise<void>;
};

export function defaultCredentialRef(providerId: string, accountId: string): string {
  return `provider-credential:${providerId}:${accountId}`;
}

function toProviderAccount(row: ProviderAccountRow): ProviderAccount {
  return {
    providerId: row.providerId,
    accountId: row.accountId,
    credentialRef: row.credentialRef,
    isDefault: row.isDefault,
    meta: row.meta,
    createdAt: row.createdAt,
    updatedAt: row.updatedAt,
  };
}

/**
 * Account registry for external provider connections (GitHub, Linear, Jira, ...).
 *
 * Metadata lives in the `provider_accounts` table; secret material lives in the
 * encrypted secrets store behind each row's `credentialRef` and never in the
 * table itself. At most one account per provider is the default, enforced by a
 * partial unique index; a missing default self-heals to the oldest account.
 */
export class ProviderAccountRegistry {
  constructor(
    private readonly database: AppDb | undefined,
    private readonly secretStore: ProviderAccountSecretStore
  ) {}

  private get db(): AppDb {
    return this.database ?? getAppDb();
  }

  async upsertAccount(input: ProviderAccountUpsert): Promise<ProviderAccountUpsertResult> {
    const existing = await this.findRow(input.providerId, input.accountId);
    const credentialRef =
      existing?.credentialRef ??
      input.credentialRef ??
      defaultCredentialRef(input.providerId, input.accountId);

    if (input.secret !== undefined) {
      await this.secretStore.setSecret(credentialRef, input.secret);
    }

    const meta: ProviderAccountMeta | undefined =
      input.meta === undefined ? undefined : { version: '1', ...input.meta };

    const row = this.db.transaction((tx): ProviderAccountRow => {
      const now = Date.now();
      const current = tx
        .select()
        .from(providerAccounts)
        .where(
          and(
            eq(providerAccounts.providerId, input.providerId),
            eq(providerAccounts.accountId, input.accountId)
          )
        )
        .get();

      if (current) {
        tx.update(providerAccounts)
          .set({ updatedAt: now, ...(meta !== undefined ? { meta } : {}) })
          .where(eq(providerAccounts.id, current.id))
          .run();
        return { ...current, updatedAt: now, meta: meta !== undefined ? meta : current.meta };
      }

      const hasDefault = tx
        .select({ id: providerAccounts.id })
        .from(providerAccounts)
        .where(
          and(
            eq(providerAccounts.providerId, input.providerId),
            eq(providerAccounts.isDefault, true)
          )
        )
        .get();

      const inserted: ProviderAccountRow = {
        id: randomUUID(),
        providerId: input.providerId,
        accountId: input.accountId,
        credentialRef,
        isDefault: !hasDefault,
        meta: meta ?? null,
        createdAt: now,
        updatedAt: now,
      };
      tx.insert(providerAccounts).values(inserted).run();
      return inserted;
    });

    return {
      account: toProviderAccount(row),
      status: existing ? 'updated' : 'created',
    };
  }

  async listAccounts(providerId: string): Promise<ProviderAccount[]> {
    const rows = await this.db
      .select()
      .from(providerAccounts)
      .where(eq(providerAccounts.providerId, providerId))
      .orderBy(asc(providerAccounts.createdAt), asc(sql`rowid`));
    return rows.map(toProviderAccount);
  }

  /**
   * Resolve one account: by id when given, otherwise the provider's default
   * account. A missing or dangling default self-heals to the oldest account.
   */
  async getAccount(providerId: string, accountId?: string): Promise<ProviderAccount | null> {
    if (accountId) {
      const row = await this.findRow(providerId, accountId);
      return row ? toProviderAccount(row) : null;
    }
    const row = this.db.transaction((tx) => this.resolveDefaultRow(tx, providerId));
    return row ? toProviderAccount(row) : null;
  }

  async getDefaultAccountId(providerId: string): Promise<string | null> {
    const account = await this.getAccount(providerId);
    return account?.accountId ?? null;
  }

  /** Make an existing account the provider default. Returns null for unknown accounts. */
  async setDefaultAccount(providerId: string, accountId: string): Promise<ProviderAccount | null> {
    const row = this.db.transaction((tx) => {
      const target = tx
        .select()
        .from(providerAccounts)
        .where(
          and(
            eq(providerAccounts.providerId, providerId),
            eq(providerAccounts.accountId, accountId)
          )
        )
        .get();
      if (!target) return null;
      if (target.isDefault) return target;

      // Clear before set: the partial unique index rejects two defaults.
      tx.update(providerAccounts)
        .set({ isDefault: false })
        .where(
          and(eq(providerAccounts.providerId, providerId), eq(providerAccounts.isDefault, true))
        )
        .run();
      tx.update(providerAccounts)
        .set({ isDefault: true })
        .where(eq(providerAccounts.id, target.id))
        .run();
      return { ...target, isDefault: true };
    });
    return row ? toProviderAccount(row) : null;
  }

  /** Read the secret stored at the account's credentialRef. */
  async resolveSecret(providerId: string, accountId?: string): Promise<string | null> {
    const account = await this.getAccount(providerId, accountId);
    if (!account) return null;
    return this.secretStore.getSecret(account.credentialRef);
  }

  /**
   * Remove one account and its secret. When the default account is removed,
   * the oldest surviving account is promoted in the same transaction.
   * Returns the removed account, or null if it did not exist.
   */
  async removeAccount(providerId: string, accountId: string): Promise<ProviderAccount | null> {
    const removed = this.db.transaction((tx) => {
      const target = tx
        .select()
        .from(providerAccounts)
        .where(
          and(
            eq(providerAccounts.providerId, providerId),
            eq(providerAccounts.accountId, accountId)
          )
        )
        .get();
      if (!target) return null;

      tx.delete(providerAccounts).where(eq(providerAccounts.id, target.id)).run();
      if (target.isDefault) {
        this.promoteOldestAccount(tx, providerId);
      }
      return target;
    });

    if (!removed) return null;
    await this.secretStore.deleteSecret(removed.credentialRef);
    return toProviderAccount(removed);
  }

  /** Remove every account (and secret) for a provider. */
  async removeAllAccounts(providerId: string): Promise<void> {
    const rows = this.db.transaction((tx) => {
      const existing = tx
        .select()
        .from(providerAccounts)
        .where(eq(providerAccounts.providerId, providerId))
        .all();
      tx.delete(providerAccounts).where(eq(providerAccounts.providerId, providerId)).run();
      return existing;
    });
    for (const row of rows) {
      await this.secretStore.deleteSecret(row.credentialRef);
    }
  }

  async isConfigured(providerId: string): Promise<boolean> {
    const row = await this.db
      .select({ id: providerAccounts.id })
      .from(providerAccounts)
      .where(eq(providerAccounts.providerId, providerId))
      .limit(1);
    return row.length > 0;
  }

  private async findRow(
    providerId: string,
    accountId: string
  ): Promise<ProviderAccountRow | undefined> {
    const rows = await this.db
      .select()
      .from(providerAccounts)
      .where(
        and(eq(providerAccounts.providerId, providerId), eq(providerAccounts.accountId, accountId))
      )
      .limit(1);
    return rows[0];
  }

  /** Find the default row, self-healing a missing default to the oldest account. */
  private resolveDefaultRow(tx: DrizzleTx, providerId: string): ProviderAccountRow | undefined {
    const current = tx
      .select()
      .from(providerAccounts)
      .where(and(eq(providerAccounts.providerId, providerId), eq(providerAccounts.isDefault, true)))
      .get();
    if (current) return current;
    return this.promoteOldestAccount(tx, providerId);
  }

  private promoteOldestAccount(tx: DrizzleTx, providerId: string): ProviderAccountRow | undefined {
    const oldest = tx
      .select()
      .from(providerAccounts)
      .where(eq(providerAccounts.providerId, providerId))
      // rowid tiebreak keeps "oldest" deterministic for same-millisecond inserts.
      .orderBy(asc(providerAccounts.createdAt), asc(sql`rowid`))
      .limit(1)
      .get();
    if (!oldest) return undefined;
    tx.update(providerAccounts)
      .set({ isDefault: true })
      .where(eq(providerAccounts.id, oldest.id))
      .run();
    return { ...oldest, isDefault: true };
  }
}
