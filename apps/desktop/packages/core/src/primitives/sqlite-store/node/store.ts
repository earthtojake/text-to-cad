import { randomUUID } from 'node:crypto';
import { rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { noopLogger, type Logger } from '@emdash/shared/logger';
import type {
  DerivedSqliteStore,
  DerivedStoreConfig,
  DurableSqliteStore,
  DurableStoreConfig,
  SqliteConnection,
  StoreHandle,
  TempMigrationHandle,
  TempStoreHandle,
} from '../api';
import { restoreLatestBackup } from './backup';
import { ensureDerivedSchema } from './derived';
import { migrateDurable } from './durable';
import { inTransaction } from './transaction';

type CommonStoreConfig<TDb, TNative> = Pick<
  DurableStoreConfig<TDb, TNative>,
  'busyTimeoutMs' | 'createOrm' | 'driver' | 'logger' | 'name'
>;

type OpenOptions = {
  cleanupOnClose?: boolean;
};

function removeDatabaseFiles(path: string): void {
  for (const suffix of ['', '-wal', '-shm']) {
    rmSync(`${path}${suffix}`, { force: true });
  }
}

function makeTempPath(name: string): string {
  const safeName = name.replaceAll(/[^a-zA-Z0-9._-]/g, '-');
  return join(tmpdir(), `emdash-${safeName}-${randomUUID()}.db`);
}

function configureConnection(connection: SqliteConnection, busyTimeoutMs: number): void {
  if (!Number.isSafeInteger(busyTimeoutMs) || busyTimeoutMs < 0) {
    throw new RangeError(`SQLite busy timeout must be a non-negative integer: ${busyTimeoutMs}`);
  }
  connection.exec('PRAGMA journal_mode = WAL');
  connection.exec(`PRAGMA busy_timeout = ${busyTimeoutMs}`);
}

function openStoreConnection<TDb, TNative, TSchemaResult>(
  config: CommonStoreConfig<TDb, TNative>,
  path: string,
  ensureSchema: (connection: SqliteConnection<TNative>, logger: Logger) => TSchemaResult,
  afterReady: (connection: SqliteConnection<TNative>, schemaResult: TSchemaResult) => void,
  onClosed: () => void,
  options: OpenOptions = {}
): StoreHandle<TDb, TNative> {
  const logger = config.logger ?? noopLogger;
  const connection = config.driver.open(path);
  let closed = false;

  try {
    configureConnection(connection, config.busyTimeoutMs ?? 5000);
    const schemaResult = ensureSchema(connection, logger);
    connection.exec('PRAGMA foreign_keys = ON');
    afterReady(connection, schemaResult);
    const db = config.createOrm ? config.createOrm(connection) : (connection as TDb);

    return {
      db,
      connection,
      transaction: <T>(operation: () => T) => {
        if (closed) throw new Error(`SQLite store ${config.name} is closed`);
        return inTransaction(connection, operation);
      },
      close: () => {
        if (closed) return;
        closed = true;
        try {
          connection.close();
        } finally {
          onClosed();
          if (options.cleanupOnClose) removeDatabaseFiles(path);
        }
      },
    };
  } catch (error) {
    try {
      connection.close();
    } finally {
      onClosed();
      if (options.cleanupOnClose) removeDatabaseFiles(path);
    }
    throw error;
  }
}

function withTempMetadata<TDb, TNative>(
  handle: StoreHandle<TDb, TNative>,
  path: string
): TempStoreHandle<TDb, TNative> {
  return { ...handle, path };
}

export function defineDurableSqliteStore<TDb = SqliteConnection, TNative = unknown>(
  config: DurableStoreConfig<TDb, TNative>
): DurableSqliteStore<TDb, TNative> {
  const openPaths = new Set<string>();
  const latestExclusiveIdx =
    config.migrations.length === 0 ? 0 : Math.max(...config.migrations.map(({ idx }) => idx)) + 1;

  const runPostMigrate = (connection: SqliteConnection): void => {
    for (const hook of config.postMigrate ?? []) hook(connection);
  };

  const runInvariants = (connection: SqliteConnection): void => {
    for (const invariant of config.invariants ?? []) invariant(connection);
  };

  const openInternal = (
    path: string,
    targetExclusiveIdx: number | undefined,
    options: OpenOptions = {}
  ): StoreHandle<TDb, TNative> => {
    const trackedPath = resolve(path);
    openPaths.add(trackedPath);
    try {
      return openStoreConnection(
        config,
        path,
        (connection, logger) =>
          migrateDurable(connection, config, logger, {
            databasePath: options.cleanupOnClose ? undefined : path,
            targetExclusiveIdx,
          }),
        (connection, { appliedCount }) => {
          if (targetExclusiveIdx !== undefined) return;
          runPostMigrate(connection);
          if (appliedCount > 0 || options.cleanupOnClose) runInvariants(connection);
        },
        () => openPaths.delete(trackedPath),
        options
      );
    } catch (error) {
      openPaths.delete(trackedPath);
      throw error;
    }
  };

  return {
    open(path) {
      return openInternal(path, undefined);
    },
    async openTemp(seed) {
      const path = makeTempPath(config.name);
      const handle = withTempMetadata(
        openInternal(path, undefined, { cleanupOnClose: true }),
        path
      );
      try {
        await seed?.(handle);
        return handle;
      } catch (error) {
        handle.close();
        throw error;
      }
    },
    openAtMigration(uptoIdx) {
      if (!Number.isSafeInteger(uptoIdx) || uptoIdx < 0 || uptoIdx > latestExclusiveIdx) {
        throw new RangeError(
          `Migration boundary must be between 0 and ${latestExclusiveIdx}: ${uptoIdx}`
        );
      }
      const path = makeTempPath(config.name);
      const handle = withTempMetadata(openInternal(path, uptoIdx, { cleanupOnClose: true }), path);
      let closed = false;
      const migrationHandle: TempMigrationHandle<TDb, TNative> = {
        ...handle,
        migrateToLatest() {
          if (closed) throw new Error(`SQLite store ${config.name} is closed`);
          migrateDurable(handle.connection, config, config.logger ?? noopLogger);
          handle.connection.exec('PRAGMA foreign_keys = ON');
          runPostMigrate(handle.connection);
          runInvariants(handle.connection);
        },
        close() {
          closed = true;
          handle.close();
        },
      };
      return migrationHandle;
    },
    restoreLatestBackup(path) {
      const trackedPath = resolve(path);
      if (openPaths.has(trackedPath)) {
        throw new Error(`Cannot restore SQLite store ${config.name} while it is open`);
      }
      restoreLatestBackup(path, config.logger ?? noopLogger);
    },
  };
}

export function defineDerivedSqliteStore<TDb = SqliteConnection, TNative = unknown>(
  config: DerivedStoreConfig<TDb, TNative>
): DerivedSqliteStore<TDb, TNative> {
  const openInternal = (path: string, options: OpenOptions = {}): StoreHandle<TDb, TNative> =>
    openStoreConnection(
      config,
      path,
      (connection, logger) => ensureDerivedSchema(connection, config, logger),
      () => {},
      () => {},
      options
    );

  return {
    open(path) {
      return openInternal(path);
    },
    async openTemp(seed) {
      const path = makeTempPath(config.name);
      const handle = withTempMetadata(openInternal(path, { cleanupOnClose: true }), path);
      try {
        await seed?.(handle);
        return handle;
      } catch (error) {
        handle.close();
        throw error;
      }
    },
  };
}
