/**
 * Unified Drizzle migration dispatcher over the five schemas in the repo:
 * the app schema plus the four stores in packages/core. Takes the target
 * schema name, runs the right db:generate script in the right package, and
 * prints the follow-up obligations so they cannot be missed.
 *
 * Usage: pnpm run db:generate <schema>
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export type DbGenerateTarget = {
  /** Package directory relative to the repo root. */
  packageDir: string;
  /** The package script that performs the generation. */
  runScript: string;
  /** Where the generated migrations land, relative to the repo root. */
  migrationsDir: string;
};

export const DB_GENERATE_TARGETS: Record<string, DbGenerateTarget> = {
  app: {
    packageDir: 'apps/emdash-desktop',
    runScript: 'db:generate:app',
    migrationsDir: 'apps/emdash-desktop/drizzle',
  },
  automations: {
    packageDir: 'packages/core',
    runScript: 'db:generate:automations',
    migrationsDir: 'packages/core/src/runtimes/automations/node/persistence/migrations',
  },
  conversations: {
    packageDir: 'packages/core',
    runScript: 'db:generate:conversations',
    migrationsDir: 'packages/core/src/runtimes/conversations/node/persistence/migrations',
  },
  'file-search': {
    packageDir: 'packages/core',
    runScript: 'db:generate:file-search',
    migrationsDir: 'packages/core/src/runtimes/file-search/node/storage/migrations',
  },
  'workspace-registry': {
    packageDir: 'packages/core',
    runScript: 'db:generate:workspace-registry',
    migrationsDir: 'packages/core/src/runtimes/workspace-registry/node/persistence/migrations',
  },
};

export function resolveDbGenerateTarget(schema: string): DbGenerateTarget | undefined {
  return DB_GENERATE_TARGETS[schema];
}

export function followUpMessage(schema: string): string {
  const target = DB_GENERATE_TARGETS[schema];
  const lines = [
    `Generated migrations for the "${schema}" schema into ${target.migrationsDir}.`,
    '',
    'Follow-up obligations before committing:',
  ];
  if (schema === 'app') {
    lines.push(
      '  1. pnpm run db:fixtures       (apps/emdash-desktop — regenerate fixture DBs)',
      '  2. pnpm run test:migrations   (apps/emdash-desktop — validate the migration)',
      '  3. Commit the drizzle/ SQL + meta, updated fixtures, and a migration test together.'
    );
  } else {
    lines.push(
      '  1. pnpm --filter @emdash/core run test   (validates the bundled migrations)',
      '  2. Commit the generated migrations and bundle output together with the schema change.'
    );
  }
  return lines.join('\n');
}

function main(): void {
  const schema = process.argv[2];
  const known = Object.keys(DB_GENERATE_TARGETS).join(', ');
  if (!schema || !resolveDbGenerateTarget(schema)) {
    console.error(`Usage: pnpm run db:generate <schema>\nKnown schemas: ${known}`);
    process.exit(1);
  }

  const target = DB_GENERATE_TARGETS[schema];
  const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..', '..');
  const result = spawnSync('pnpm', ['run', target.runScript], {
    stdio: 'inherit',
    cwd: path.join(repoRoot, target.packageDir),
    shell: process.platform === 'win32',
  });
  if (result.error) {
    console.error(`db:generate: failed to run ${target.runScript}:`, result.error);
    process.exit(1);
  }
  if (result.status !== 0) {
    process.exit(typeof result.status === 'number' ? result.status : 1);
  }

  console.log(`\n${followUpMessage(schema)}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
