import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import type { BundledMigration } from '../api';

type JournalEntry = {
  idx: number;
  when: number;
  tag: string;
  breakpoints: boolean;
};

type Journal = {
  entries: JournalEntry[];
};

/**
 * Reads a drizzle-kit `out` directory and returns the migration chain as
 * `BundledMigration[]`, ready to pass to `defineDurableSqliteStore`.
 *
 * The function is pure I/O over the filesystem — it knows nothing about
 * domain schemas or store names. Hash is SHA-256 of the raw SQL file bytes,
 * matching the durable migration runner's verification.
 */
export function readDrizzleMigrations(outDir: string): readonly BundledMigration[] {
  const journalPath = join(outDir, 'meta', '_journal.json');
  const journal: Journal = JSON.parse(readFileSync(journalPath, 'utf-8'));

  return journal.entries.map((entry) => {
    const sqlPath = join(outDir, `${entry.tag}.sql`);
    const sqlBytes = readFileSync(sqlPath);
    const hash = createHash('sha256').update(sqlBytes).digest('hex');
    const sql = sqlBytes.toString('utf-8');

    return { idx: entry.idx, tag: entry.tag, when: entry.when, hash, sql };
  });
}

/**
 * Renders `BundledMigration[]` as a self-contained TypeScript module string.
 * The caller is responsible for writing the file and formatting it.
 */
export function renderBundledMigrationsModule(migrations: readonly BundledMigration[]): string {
  const lines = [
    '// AUTO-GENERATED — do not edit. Re-run the bundle-drizzle-migrations script.',
    "import type { BundledMigration } from '#primitives/sqlite-store/api';",
    '',
    'export const migrations: readonly BundledMigration[] = [',
  ];

  for (const m of migrations) {
    lines.push('  {');
    lines.push(`    idx: ${m.idx},`);
    lines.push(`    tag: ${JSON.stringify(m.tag)},`);
    lines.push(`    when: ${m.when},`);
    lines.push(`    hash: ${JSON.stringify(m.hash)},`);
    lines.push(`    sql: ${JSON.stringify(m.sql)},`);
    lines.push('  },');
  }

  lines.push('];');
  lines.push('');

  return lines.join('\n');
}

/**
 * Lists the `.sql` files in a drizzle-kit `out` directory that are referenced
 * by the journal. Useful for verifying no orphaned or missing files.
 */
export function listMigrationSqlFiles(outDir: string): string[] {
  return readdirSync(outDir)
    .filter((f) => f.endsWith('.sql'))
    .sort();
}
