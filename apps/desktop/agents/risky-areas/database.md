# Risky Area: Database

## Main Files

- `src/core/services/app-db/node/schema.ts`
- `src/main/db/initialize.ts`
- `drizzle/`

## Rules

- never hand-edit numbered migrations
- never hand-edit `drizzle/meta/`
- use `pnpm exec drizzle-kit generate` for new migrations
- treat schema invariants and data migrations as high risk

## Current Behavior

- portable schema, row types, and Drizzle helpers live in `src/core/services/app-db/node/`
- database path is resolved by main-process db path helpers
- `EMDASH_DB_FILE` overrides the default location
- the main bootstrap creates one native Drizzle client and passes its SQLite connection to
  `src/main/db/initialize.ts`
- Core Node services receive `AppDb` through constructor/factory injection
- main free-function code uses the throwing `@main/db/instance` accessor at call time
- shutdown closes and clears the initialized database after scoped services are disposed

## Development Workflow

### Tooling folder

All dev and test infrastructure lives in `tooling/` inside `apps/emdash-desktop/`.
Nothing in `tooling/` is part of the production Electron bundle — the `@tooling`
alias only exists in `vitest.config.ts`, not in `electron.vite.config.ts`.

```
tooling/
├── fixtures/           committed SQLite snapshots (empty.db, baseline.db)
├── node-deps/          isolated better-sqlite3 compiled for system Node
├── seeds/              seed functions that populate fixtures
├── generate-fixtures.ts  fixture generator script (run via vitest)
└── utils/
    └── db.ts           openFixture() helper for migration tests
```

### Isolated dev database

Point `EMDASH_DB_FILE` at a scratch path instead of using the default database
when working on migrations, so schema experiments cannot corrupt your real app
data. `pnpm run db:reset` wipes the default dev databases.

```bash
EMDASH_DB_FILE=/tmp/emdash-scratch.db pnpm run dev   # start app with isolated dev database
pnpm run db:reset                                    # wipe the dev databases and start fresh
```

### Fixture databases

Two committed SQLite snapshots live in `tooling/fixtures/`:

- `empty.db` — all migrations applied, no data
- `baseline.db` — 2 projects, 4 tasks, conversations (see seeds in `tooling/seeds/`)

Regenerate after any schema change:

```bash
pnpm run db:fixtures   # writes .db files — no rebuild needed
```

`db:fixtures` and `test:migrations` use an isolated copy of `better-sqlite3`
installed under `tooling/node-deps/` (compiled for system Node). The app's
`node_modules/better-sqlite3` stays Electron-compiled at all times.

### Migration authoring checklist

1. **Isolate your dev DB**: run the app with `EMDASH_DB_FILE` pointing at a scratch path
   so you're not working against your personal emdash database

2. **Snapshot the pre-migration baseline**:
   ```bash
   cp tooling/fixtures/baseline.db tooling/fixtures/pre-XXXX.db
   ```
   Commit this snapshot. It is the starting state your migration test will run against.

3. **Write the migration**: edit `src/core/services/app-db/node/schema.ts`, then generate the SQL:
   ```bash
   pnpm run db:generate
   ```

4. **Write a migration test** in `src/main/db/tests/migrations/` using `openFixture('pre-XXXX')`.
   See `example.test.ts` in that directory for the pattern.

5. **Regenerate fixtures** so `baseline.db` and `empty.db` include the new schema:
   ```bash
   pnpm run db:fixtures
   ```

6. **Run migration tests**:
   ```bash
   pnpm run test:migrations
   ```

7. **Commit everything together**: migration SQL (`drizzle/`), `drizzle/meta/`,
   `pre-XXXX.db`, updated `tooling/fixtures/*.db`, the migration test.

## Versioned JSON columns

### What they are

Some `text()` columns store structured JSON that may evolve across app versions.
These columns use `versionedJsonColumn()` — a Drizzle `customType` that
transparently handles version detection, upgrade chains, and serialization.

```ts
import { versionedJsonColumn } from '@core/services/app-db/node/versioned-column';
import { myConfig } from '@core/primitives/my-domain/api/my-config';

export const myTable = sqliteTable('my_table', {
  col: versionedJsonColumn(myConfig)('col'),
  // inferred type: MyConfig | null
});
```

Drizzle's `fromDriver` runs the full upgrade chain on read. `toDriver` always
serializes the latest version on write. No `JSON.parse` or `JSON.stringify` is
needed at call sites.

### Schema definitions

Versioned schema definitions live in the owning `src/core/primitives/<domain>/api/` slice. See
`agents/conventions/versioned-schemas.md` for the full guide including the
`defineVersionedSchema()` builder API, upgrade function patterns, and testing
guidance.

### Column inventory

| Column | Schema file |
|--------|-------------|
| `workspaces.config` | `src/core/primitives/workspaces/api/workspace-config.ts` |
| `conversations.config` | `src/core/primitives/conversations/api/conversation-config.ts` |
| `tasks.task_config` | `src/core/primitives/tasks/api/task-config.ts` |
| `tasks.linked_issue` | `src/core/primitives/linked-issues/api/linked-issue.ts` |
| `automations.trigger_config` | `src/core/primitives/automations/api/config.ts` |
| `automations.conversation_config` | `src/core/primitives/automations/api/config.ts` |
| `automations.task_config` | `src/core/primitives/automations/api/config.ts` |
| `ssh_connections.metadata` | `src/core/primitives/ssh/api/ssh-connection-metadata.ts` |

### Snapshot columns and raw SQL

`versionedJsonColumn` only hooks into ORM-level reads and writes. Columns written
via raw SQL in automation run snapshots bypass `fromDriver`/`toDriver`. Those
columns remain `text()` — call `schema.parseJson(row.col)` explicitly on read and
`JSON.stringify` on write.

### Risky operations

- **Removing a field from a schema**: always keep the field as `.optional()` or
  provide an upgrade function that drops it. Removing it silently breaks old rows
  that still carry the field.
- **Renaming a field**: requires a new version with an upgrade function.
- **Changing a field type in place**: requires a new version. Never change a field
  type within an existing version.
- **Adding a required field without a default**: must either be `.optional()` or
  require an upgrade function that supplies a default value.

### Testing utilities

- `openFixture(name)` in `tooling/utils/db.ts` — copies a named fixture to a
  temp file, applies any pending migrations (via our own `initializeDatabase()`),
  returns a `DrizzleClient`. Each call is fully isolated; `close()` deletes the temp file.
  Import via `@tooling/utils/db` (alias available in all Vitest projects).
- Migration tests live in `src/main/db/tests/migrations/` and run via
  `pnpm run test:migrations` (separate from the main test suite because they
  use `import.meta.glob`, which requires Vite's transform pipeline).
