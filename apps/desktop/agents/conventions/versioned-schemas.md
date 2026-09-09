# Versioned JSON Column Schemas

## Why versioned schemas?

Emdash is a desktop app. Users may run an older version for weeks or months before
updating. JSON blobs stored in SQLite columns must remain readable by any app version
that could encounter them, so schema evolution must be explicit and backward compatible.

The versioned schema system handles this transparently:

- **Version detection** — reads the `version` field first, before any parsing.
- **Sequential upgrade chain** — applies upgrade functions one step at a time until
  the latest version is reached.
- **Forward-only reads** — data written by a newer app version is surfaced as a
  `future-version` result so the older app can degrade gracefully rather than corrupt.
- **Latest-version writes** — serialization always writes the current version.
- **Dev-only validation** — Zod parsing runs in development to catch drift; in
  production only the upgrade chain runs (no re-validation cost).

## When to use a versioned schema

Add a `VersionedSchema` whenever:

- A `text()` Drizzle column stores structured JSON (not an opaque string).
- The shape of the JSON may need to evolve in a future release.
- Multiple app versions will coexist and share the same database.

If the column stores a plain non-structured string (e.g. a path, a status label, or
a serialized non-JSON value), a versioned schema is not necessary.

## Key files

| File | Purpose |
|------|---------|
| `packages/core/src/primitives/versioned-schema/api/versioned-schema.ts` | Core utility: `VersionedSchema`, `defineVersionedSchema`, `ParseResult` (imported as `@emdash/core/primitives/versioned-schema/api`) |
| `src/core/services/app-db/node/versioned-column.ts` | Drizzle integration: `versionedJsonColumn`, `parseVersionedColumn`, `serializeVersionedColumn` |

## Defining a versioned schema

Schema definitions live in the owning `src/core/primitives/<domain>/api/` slice so they can be
imported by both Node and browser surfaces.

### Schemas that started versioned from day one

Use `.initial()` if the stored JSON always had a `version` field from the start:

```ts
// src/core/primitives/my-domain/api/my-config.ts
import z from 'zod';
import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';

const v1Schema = z.object({
  version: z.literal('1'),
  name: z.string(),
});

export const myConfig = defineVersionedSchema()
  .initial('1', v1Schema)
  .build();

export type MyConfig = typeof myConfig.Type;
```

### Schemas for legacy data without a version field

Use `.unversioned()` when the column was first written before the versioning system
existed (the data has no `version` field):

```ts
// src/core/primitives/my-domain/api/my-config.ts
const v0Schema = z.object({
  name: z.string(),
  value: z.number().optional(),
});

export const myConfig = defineVersionedSchema()
  .unversioned(v0Schema)
  .build();

export type MyConfig = typeof myConfig.Type;
```

### Adding a new version with an upgrade function

Chain `.version()` to add a new version. The upgrade function receives the
**validated** previous-version object and must return the new-version object, or
`null` if external context is required to upgrade:

```ts
const v2Schema = z.object({
  version: z.literal('2'),
  name: z.string(),
  label: z.string(),        // new required field
  value: z.number().optional(),
});

export const myConfig = defineVersionedSchema()
  .unversioned(v0Schema)
  .version('2', v2Schema, (v0) => ({
    version: '2' as const,
    name: v0.name,
    label: v0.name,           // derive from existing data
    value: v0.value,
  }))
  .build();
```

Return `null` from an upgrade function when the caller must supply a context value
not available in the stored data. `safeParse()` will return `{ status: 'needs-context' }`.

## Wiring the Drizzle column

In `src/core/services/app-db/node/schema.ts`, replace `text('col_name')` with
`versionedJsonColumn`:

```ts
import { versionedJsonColumn } from '@core/services/app-db/node/versioned-column';
import { myConfig } from '@core/primitives/my-domain/api/my-config';

export const myTable = sqliteTable('my_table', {
  // Before:
  // col: text('col'),
  // After:
  col: versionedJsonColumn(myConfig)('col'),
});
```

Drizzle infers the TypeScript type as `MyConfig | null` for both reads and writes.
No `JSON.parse` or `JSON.stringify` is needed at any call site.

## Removing manual parse/serialize at call sites

After wiring `versionedJsonColumn`, remove any manual serialization in write paths
and any manual parsing in read paths:

```ts
// Before
await db.update(myTable).set({ col: JSON.stringify(value) });
const parsed = JSON.parse(row.col) as MyConfig;

// After
await db.update(myTable).set({ col: value });
const parsed = row.col; // already MyConfig | null
```

## Nesting a versioned schema inside another

Use `.asNested()` to embed one versioned schema as a field of another Zod object.
This allows parent upgrade functions to call child upgrade logic automatically:

```ts
import { childConfig } from '@core/primitives/my-domain/api/child-config';

const parentV1Schema = z.object({
  version: z.literal('1'),
  child: childConfig.asNested().optional(),
});

export const parentConfig = defineVersionedSchema()
  .initial('1', parentV1Schema)
  .build();
```

> **Note**: `asNested()` uses Zod's `.transform()` internally. Parent schemas that
> use it cannot be validated with `z.encode()`.

## Reading the parse result directly

When you need fine-grained control (e.g. snapshot columns that bypass Drizzle
`customType`), call `parseJson()` or `safeParse()` directly:

```ts
// parseJson: convenience wrapper for JSON string columns
const data = myConfig.parseJson(row.rawJsonString); // MyConfig | null

// safeParse: discriminated union with full detail
const result = myConfig.safeParse(parsed);
if (result.status === 'ok') { /* result.data: MyConfig */ }
if (result.status === 'needs-context') { /* result.version, result.raw */ }
if (result.status === 'future-version') { /* result.version */ }
if (result.status === 'invalid') { /* result.reason */ }
```

## Snapshot columns and raw SQL

Drizzle `customType` only runs `fromDriver` / `toDriver` for ORM-level reads and
writes. Snapshot columns written via raw SQL (e.g. in automation run triggers) bypass
these hooks. For those columns, keep the column as `text()` and call `parseJson()`
explicitly on read:

```ts
const snapshot = automationTriggerConfig.parseJson(row.triggerConfigSnapshot);
```

## Testing

Test versioned schemas directly without going through Drizzle:

```ts
import { myConfig } from '@core/primitives/my-domain/api/my-config';

it('parses a v0 object', () => {
  const result = myConfig.safeParse({ name: 'hello' });
  expect(result).toEqual({ status: 'ok', data: { name: 'hello' } });
});

it('upgrades v0 → v2', () => {
  const result = myConfig.safeParse({ name: 'hello' });
  expect(result.status).toBe('ok');
  if (result.status === 'ok') expect(result.data.label).toBe('hello');
});

it('round-trips through serialize/parseJson', () => {
  const value = myConfig.schema.parse({ version: '2', name: 'x', label: 'x' });
  expect(myConfig.parseJson(myConfig.serialize(value))).toEqual(value);
});
```

For Drizzle column helpers, use the exported `parseVersionedColumn` and
`serializeVersionedColumn` functions from `src/core/services/app-db/node/versioned-column.ts`.

## All migrated columns

| Column | Schema file | Versioning |
|--------|-------------|------------|
| `workspaces.config` | `src/core/primitives/workspaces/api/workspace-config.ts` | v1 → v2 (versioned from start) |
| `conversations.config` | `src/core/primitives/conversations/api/conversation-config.ts` | unversioned (v0) |
| `automations.trigger_config` | `src/core/primitives/automations/api/config.ts` | unversioned (v0) |
| `automations.conversation_config` | `src/core/primitives/automations/api/config.ts` | unversioned (v0) |
| `automations.task_config` | `src/core/primitives/automations/api/config.ts` | v1 (versioned from start) |
| `ssh_connections.metadata` | `src/core/primitives/ssh/api/ssh-connection-metadata.ts` | unversioned (v0) |
| `tasks.linked_issue` | `src/core/primitives/linked-issues/api/linked-issue.ts` | unversioned (v0) |
| `workspaces.data` | `src/core/primitives/workspaces/api/workspace-provider-data.ts` | unversioned (v0) |
| `tasks.task_config` | `src/core/primitives/tasks/api/task-config.ts` | v1 (versioned from start) |
