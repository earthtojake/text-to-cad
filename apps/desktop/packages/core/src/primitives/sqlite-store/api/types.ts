import type { Logger } from '@emdash/shared/logger';
import type { SqliteConnection, SqliteDriver } from './driver';

export type BundledMigration = {
  idx: number;
  tag: string;
  /** Legacy Drizzle journal timestamp in milliseconds. */
  when: number;
  /** SHA-256 of the raw migration SQL bytes. */
  hash: string;
  sql: string;
};

export type AppliedMigration = {
  tag: string;
  hash: string;
};

export interface MigrationInterop {
  /** Called once inside the runner bootstrap transaction. */
  backfill?(connection: SqliteConnection, migrations: readonly BundledMigration[]): void;
  /** Called inside the same transaction that records an applied migration. */
  onApplied?(connection: SqliteConnection, migration: BundledMigration): void;
}

export type StoreHandle<TDb, TNative = unknown> = {
  readonly db: TDb;
  readonly connection: SqliteConnection<TNative>;
  /** Transactions are synchronous; the callback must not return a promise. */
  transaction<T>(operation: () => T): T;
  close(): void;
};

export type TempStoreHandle<TDb, TNative = unknown> = StoreHandle<TDb, TNative> & {
  readonly path: string;
};

export type TempMigrationHandle<TDb, TNative = unknown> = TempStoreHandle<TDb, TNative> & {
  migrateToLatest(): void;
};

type BaseStoreConfig<TDb, TNative = unknown> = {
  name: string;
  driver: SqliteDriver<TNative>;
  createOrm?: (connection: SqliteConnection<TNative>) => TDb;
  busyTimeoutMs?: number;
  logger?: Logger;
};

export type DurableStoreConfig<TDb = SqliteConnection, TNative = unknown> = BaseStoreConfig<
  TDb,
  TNative
> & {
  migrations: readonly BundledMigration[];
  interop?: MigrationInterop;
  backup?: {
    retain: number;
  };
  postMigrate?: readonly ((connection: SqliteConnection) => void)[];
  invariants?: readonly ((connection: SqliteConnection) => void)[];
};

export type DerivedStoreConfig<TDb = SqliteConnection, TNative = unknown> = BaseStoreConfig<
  TDb,
  TNative
> & {
  version: number;
  createSchema(connection: SqliteConnection<TNative>): void;
};

export interface SqliteStoreBase<TDb, TNative = unknown> {
  open(path: string): StoreHandle<TDb, TNative>;
  openTemp(
    seed?: (handle: StoreHandle<TDb, TNative>) => void | Promise<void>
  ): Promise<TempStoreHandle<TDb, TNative>>;
}

export interface DurableSqliteStore<TDb, TNative = unknown> extends SqliteStoreBase<TDb, TNative> {
  openAtMigration(uptoIdx: number): TempMigrationHandle<TDb, TNative>;
  restoreLatestBackup(path: string): void;
}

export type DerivedSqliteStore<TDb, TNative = unknown> = SqliteStoreBase<TDb, TNative>;
