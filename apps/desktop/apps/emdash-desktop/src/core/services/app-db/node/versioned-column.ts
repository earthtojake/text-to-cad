import type { VersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { log } from '@emdash/shared/logger';
import { customType } from 'drizzle-orm/sqlite-core';

/**
 * Parses a raw TEXT column value into a typed domain object using a versioned
 * schema. Handles version detection, upgrade chain execution, and error logging.
 * Returns `null` on any failure — never throws.
 *
 * Exported separately from `versionedJsonColumn` so it can be tested in isolation
 * without accessing Drizzle's protected `ColumnBuilder.config` property.
 */
export function parseVersionedColumn<T>(
  schema: VersionedSchema<T>,
  value: string | null
): T | null {
  if (!value) return null;

  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    log.warn('[versionedJson] Failed to JSON.parse stored column value');
    return null;
  }

  const result = schema.safeParse(parsed);

  if (result.status === 'ok') {
    return result.data;
  }

  if (result.status === 'future-version') {
    log.warn('[versionedJson] Future schema version encountered — app update may be needed', {
      version: result.version,
    });
  } else if (result.status === 'needs-context') {
    log.warn('[versionedJson] Schema upgrade requires external context', {
      version: result.version,
    });
  } else {
    log.warn('[versionedJson] Failed to parse versioned column', { reason: result.reason });
  }

  return null;
}

/**
 * Serializes a typed domain object to a JSON string for storage. Returns `null`
 * for null/undefined input.
 *
 * Exported separately from `versionedJsonColumn` so it can be tested in isolation.
 */
export function serializeVersionedColumn<T>(
  schema: VersionedSchema<T>,
  value: T | null | undefined
): string | null {
  if (value === null || value === undefined) return null;
  return schema.serialize(value);
}

/**
 * Creates a Drizzle SQLite column type that transparently handles versioned
 * JSON schema parsing on read and latest-version serialization on write.
 *
 * On read  (fromDriver): TEXT -> JSON.parse -> version check -> upgrade chain -> T | null
 * On write (toDriver):   T -> JSON.stringify (always writes the latest version)
 *
 * The column always returns `T | null`:
 * - `null` for SQL NULL values
 * - `null` when the stored JSON cannot be parsed into any known version
 * - `null` for future-version data (written by a newer app release)
 * - `null` for data requiring external context to upgrade (needs-context)
 *
 * Failures are logged as warnings but never thrown — a single corrupt row
 * will not crash an entire DB query.
 *
 * @example
 * ```ts
 * import { workspaceConfig } from '@core/primitives/workspaces/api';
 *
 * export const workspaces = sqliteTable('workspaces', {
 *   config: versionedJsonColumn(workspaceConfig)('config'),
 * });
 * // workspaces.config is typed as WorkspaceConfig | null
 * ```
 */
export function versionedJsonColumn<T>(schema: VersionedSchema<T>) {
  return customType<{ data: T | null; driverData: string | null }>({
    dataType() {
      return 'text';
    },
    fromDriver(value: string | null): T | null {
      return parseVersionedColumn(schema, value);
    },
    toDriver(value: T | null): string | null {
      return serializeVersionedColumn(schema, value);
    },
  });
}
