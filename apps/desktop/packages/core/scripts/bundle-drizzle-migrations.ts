import { writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import {
  readDrizzleMigrations,
  renderBundledMigrationsModule,
} from '../src/primitives/sqlite-store/node/bundle-drizzle-migrations';

const migrationsDir = process.argv[2];
if (!migrationsDir) {
  console.error('Usage: tsx scripts/bundle-drizzle-migrations.ts <migrations-dir>');
  process.exit(1);
}

const outDir = resolve(migrationsDir);
const migrations = readDrizzleMigrations(outDir);
const output = renderBundledMigrationsModule(migrations);
const outFile = join(outDir, 'migrations.generated.ts');

writeFileSync(outFile, output, 'utf-8');
console.log(`Bundled ${migrations.length} migration(s) → ${outFile}`);
