import { createRequire } from 'node:module';
import type * as DrizzleKitApi from 'drizzle-kit/api';

const require = createRequire(import.meta.url);
const { generateSQLiteDrizzleJson, generateSQLiteMigration } =
  require('drizzle-kit/api') as typeof DrizzleKitApi;

export type DrizzleSchemaExports = Record<string, unknown>;

/**
 * Compiles a Drizzle SQLite schema into the SQL required to create it from scratch.
 *
 * This is a build-time helper. Consumers should emit the returned statements into a
 * generated source module rather than importing drizzle-kit in a runtime bundle.
 */
export async function compileDrizzleSchemaToSql(schema: DrizzleSchemaExports): Promise<string[]> {
  const orderedSchema = Object.fromEntries(
    Object.entries(schema).sort(([left], [right]) => left.localeCompare(right))
  );
  const [empty, target] = await Promise.all([
    generateSQLiteDrizzleJson({}),
    generateSQLiteDrizzleJson(orderedSchema),
  ]);
  return await generateSQLiteMigration(empty, target);
}
