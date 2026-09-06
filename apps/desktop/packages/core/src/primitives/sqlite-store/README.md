# SQLite stores

`sqlite-store` standardizes how Emdash opens, migrates, tests, backs up, and
rebuilds SQLite files. It deliberately does not depend on an ORM or a particular
SQLite package. A host supplies a `SqliteDriver` and may attach an ORM through
`createOrm`.

## Choose a store type

| Concern | Durable store | Derived store |
| --- | --- | --- |
| Intended data | User-authored or otherwise irreplaceable | Cache or index reproducible from another source |
| Schema changes | Ordered migration history | Drop and rebuild |
| Version state | `__emdash_migrations` plus runner metadata | Schema fingerprint in `PRAGMA user_version` |
| Backups | Optional, before pending migrations | Not supported |
| Downgrade behavior | Unknown newer migration rows are tolerated | Any version mismatch rebuilds |
| Migration tests | `openAtMigration()` | Rebuild/idempotence tests |

Use `defineDurableSqliteStore()` unless losing the whole database is always safe.
A derived store's `createSchema` must be capable of recreating everything from
scratch at any time.

## Defining stores

### Durable

The application owns the driver adapter and ORM attachment:

```ts
import { defineDurableSqliteStore } from '@emdash/core/primitives/sqlite-store/node';
import { assertSqliteStoreInvariants } from '@emdash/core/primitives/sqlite-store/testing';
import { drizzle } from 'drizzle-orm/better-sqlite3';
import { betterSqlite3Driver } from './better-sqlite3-driver';
import { migrations } from './migrations.generated';
import * as schema from './schema';

export const appStore = defineDurableSqliteStore({
  name: 'app',
  driver: betterSqlite3Driver,
  migrations,
  createOrm: (connection) => drizzle(connection.native, { schema }),
  backup: { retain: 2 },
  invariants: [assertSqliteStoreInvariants],
});

const handle = appStore.open('/path/to/emdash.db');
handle.db.select().from(schema.projects);
handle.close();
```

`createOrm` is optional. Without it, `handle.db` is the `SqliteConnection`.
`postMigrate` hooks run with foreign keys enabled whenever the latest schema is
opened. `invariants` run after those hooks when migrations were applied, for
every `openTemp()`, and after every `migrateToLatest()`. No-op production opens
skip invariants so full database scans do not become a startup cost.

### Derived

```ts
import {
  defineDerivedSqliteStore,
  fingerprintDerivedSchema,
  betterSqlite3Driver,
} from '@emdash/core/primitives/sqlite-store/node';

const schemaSql = `
  CREATE TABLE indexed_paths (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL
  ) STRICT
`;

export const searchStore = defineDerivedSqliteStore({
  name: 'file-search',
  driver: betterSqlite3Driver,
  version: fingerprintDerivedSchema(schemaSql),
  createSchema(connection) {
    connection.exec(schemaSql);
  },
});
```

When `user_version` is lower or higher than `version`, the primitive removes all
non-internal schema objects, calls `createSchema`, and stamps the requested
version in one transaction. Rebuilding a higher version is intentional: derived
stores remain usable after an application downgrade.

`fingerprintDerivedSchema()` converts the schema SQL itself into a positive
31-bit `user_version`. It normalizes formatting whitespace outside quoted SQL
values before computing SHA-256, so reformatting or changing line endings does
not rebuild production stores. Meaningful DDL and quoted-value changes do. Pass
the exact SQL constant executed by `createSchema`; when schema codegen is added,
compute the fingerprint from generator input before formatting generated
TypeScript.

#### Build-time Drizzle codegen

`@emdash/core/primitives/sqlite-store/codegen` exposes
`compileDrizzleSchemaToSql(schema)`. It uses `drizzle-kit/api` entirely in
memory to diff an empty SQLite snapshot against imported Drizzle table exports.
The helper sorts export keys before compilation so generated DDL is stable
across module loaders.

Keep this import in build scripts and drift tests only. Runtime stores should
import a checked-in generated statement array, compute their fingerprint from
that array, and never bundle `drizzle-kit`.

## Driver contract

`SqliteConnection` exposes only:

- `exec(sql)` for DDL and multi-statement SQL;
- `get`, `all`, and `run` for prepared statements;
- `close`;
- `native` as an escape hatch for ORM attachment.

The store—not the driver—owns pragmas and transaction behavior. Every open sets
WAL mode, `busy_timeout`, and foreign-key enforcement. Transactions use explicit
`BEGIN IMMEDIATE`, `COMMIT`, and `ROLLBACK`, so different drivers cannot
silently change migration semantics. Transaction callbacks must be synchronous.

Use `runSqliteDriverConformance()` from the testing entry point when adding a
driver. It verifies multi-statement execution, parameter binding, result shape,
TEXT/INTEGER/BLOB/NULL round trips, exact large integers, runner pragmas,
foreign-key toggling, transaction semantics, and `VACUUM INTO`.

## Durable migrations

A bundled migration contains stable identity and raw SQL:

```ts
type BundledMigration = {
  idx: number;
  tag: string;
  when: number; // legacy Drizzle journal milliseconds
  hash: string; // SHA-256 of raw SQL file bytes
  sql: string;
};
```

The runner:

1. Bootstraps its bookkeeping schema when `user_version` is zero.
2. Reads applied tags and verifies hashes for migrations known to this binary.
3. Computes pending work by tag set difference, ordered by `idx`.
4. Creates a backup when configured and a persistent database needs work.
5. Disables foreign keys **before** opening migration transactions.
6. Applies each migration atomically, splitting Drizzle SQL on
   `--> statement-breakpoint`.
7. Records `(tag, hash, applied_at)` in `__emdash_migrations`.
8. Runs optional interop inside the same transaction.
9. Runs `PRAGMA foreign_key_check`, then reenables enforcement in `finally`.

Rows for migrations unknown to an older binary are ignored. This allows additive
database upgrades to remain downgrade-tolerant. A known tag with a different
hash throws because shipped migration SQL is immutable.

Durable migration hashes are SHA-256 of the raw SQL file bytes. The algorithm
is part of the runner schema contract rather than a per-row `hash_algo` column:
changing it requires a `RUNNER_SCHEMA_VERSION` bump that explicitly rewrites
bookkeeping. Derived fingerprints need no stored algorithm because a changed
implementation causes one safe rebuild and then becomes self-consistent.

SQLite ignores `PRAGMA foreign_keys` changes inside a transaction. Migration SQL
may contain those pragmas, but correctness comes from the outer runner protocol.

### Legacy migration interop

Migration history conversion is optional and pluggable:

```ts
type MigrationInterop = {
  backfill?(connection, migrations): void;
  onApplied?(connection, migration): void;
};
```

`backfill` runs once inside the bookkeeping bootstrap transaction. `onApplied`
runs inside each migration transaction after the new bookkeeping row is
inserted.

`drizzleV0Interop` supports databases written by Drizzle's v0 journal layout. It:

- reads `__drizzle_migrations`;
- matches rows by `created_at === migration.when`, falling back to SQL hash;
- throws rather than guessing if a row cannot be identified;
- dual-writes newly applied migrations to `__drizzle_migrations`.

Dual-write keeps older application binaries from reapplying migrations after a
downgrade. Configure this interop only for stores with that legacy history.

## Backups and restore

Durable stores with `backup: { retain: N }` create consistent sibling backups
using `VACUUM INTO` before pending migrations. Paths are SQL-escaped, and old
backups are pruned by the creation timestamp embedded in their filename.

Call `restoreLatestBackup(path)` only when every handle for that store path is
closed. Restore removes stale WAL/SHM sidecars and replaces the database through
a temporary file. The method refuses to run while the path is open.
That open-path guard is scoped to one store instance; callers must share the
defined store rather than independently defining stores for the same file.

## Testing

### Fully migrated temporary database

`openTemp` creates an isolated on-disk database, applies all migrations, awaits
the optional seed, and deletes the database plus WAL/SHM files on close:

```ts
const handle = await appStore.openTemp(async ({ db }) => {
  await db.insert(projects).values({ id: 'project-1', name: 'Example' });
});

try {
  // test against handle.db or handle.connection
} finally {
  handle.close();
}
```

It is intentionally file-backed rather than `:memory:` so WAL, backup, and
multi-connection behavior stay representative.

### Testing a specific migration

`openAtMigration(n)` applies migrations whose `idx < n`. Seed pre-migration data
with raw SQL, because latest-schema ORM types cannot faithfully describe an old
schema:

```ts
const handle = appStore.openAtMigration(18);
try {
  handle.connection.exec(`
    INSERT INTO workspaces (id, type, ssh_connection_id)
    VALUES ('workspace-1', 'project-ssh', 'missing-ssh')
  `);

  handle.migrateToLatest();
  assertSqliteStoreInvariants(handle.connection);
} finally {
  handle.close();
}
```

This replaces opaque binary pre-migration fixtures with reviewable, adversarial
test setup. `openAtMigration` and backup/restore exist only on the durable store
type.

`assertIncrementalMigrationEquivalence(store, migrationCount)` opens every
historical migration boundary, migrates it to latest, and compares its
`sqlite_schema` with a one-shot latest database. Use it as a compact regression
test for the complete migration chain.

## Invariants

- Never edit SQL for a shipped migration. Hash verification will reject it.
- Hash raw UTF-8 file bytes without trimming or line-ending normalization.
- Preserve legacy `when` milliseconds while `drizzleV0Interop` is needed.
- `PRAGMA user_version` belongs exclusively to the store primitive: durable
  stores use it for runner metadata; derived stores use it for a schema
  fingerprint.
- Domain code must not read or write `user_version`.
- Derived data must be safe to delete at any time.
- Store initialization after migration throws on integrity failures.
  `assertSqliteIntegrity` runs SQLite's full B-tree and index consistency check;
  `assertForeignKeyIntegrity` scans for orphaned references. This intentionally
  differs from expected operational failures that use `Result`: callers cannot
  safely continue with an unidentified or corrupt schema.
