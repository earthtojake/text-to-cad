import type { AppliedMigration, BundledMigration } from './types';

export function validateMigrationManifest(migrations: readonly BundledMigration[]): void {
  const tags = new Set<string>();
  const indices = new Set<number>();

  for (const migration of migrations) {
    if (!migration.tag) throw new Error('Migration tags must not be empty');
    if (!Number.isSafeInteger(migration.idx) || migration.idx < 0) {
      throw new Error(`Migration ${migration.tag} has invalid index ${migration.idx}`);
    }
    if (tags.has(migration.tag)) {
      throw new Error(`Duplicate migration tag: ${migration.tag}`);
    }
    if (indices.has(migration.idx)) {
      throw new Error(`Duplicate migration index: ${migration.idx}`);
    }
    tags.add(migration.tag);
    indices.add(migration.idx);
  }
}

export function verifyAppliedHashes(
  applied: readonly AppliedMigration[],
  migrations: readonly BundledMigration[]
): void {
  const expectedByTag = new Map(migrations.map((migration) => [migration.tag, migration.hash]));

  for (const row of applied) {
    const expected = expectedByTag.get(row.tag);
    // A newer application may have added migrations that this version does not
    // know about. Ignore those rows to preserve downgrade compatibility.
    if (expected === undefined) continue;
    if (row.hash !== expected) {
      throw new Error(`Migration ${row.tag} was modified after it was applied`);
    }
  }
}

export function computePendingMigrations(
  applied: readonly AppliedMigration[],
  migrations: readonly BundledMigration[]
): BundledMigration[] {
  validateMigrationManifest(migrations);
  verifyAppliedHashes(applied, migrations);
  const appliedTags = new Set(applied.map((migration) => migration.tag));
  return migrations
    .filter((migration) => !appliedTags.has(migration.tag))
    .sort((left, right) => left.idx - right.idx);
}
