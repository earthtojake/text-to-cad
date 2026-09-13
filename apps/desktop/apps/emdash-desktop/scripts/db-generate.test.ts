import { describe, expect, it } from 'vitest';
import { DB_GENERATE_TARGETS, followUpMessage, resolveDbGenerateTarget } from './db-generate.ts';

describe('resolveDbGenerateTarget', () => {
  it('covers all five schemas', () => {
    expect(Object.keys(DB_GENERATE_TARGETS).sort()).toEqual([
      'app',
      'automations',
      'conversations',
      'file-search',
      'workspace-registry',
    ]);
  });

  it('maps the app schema to the app package and drizzle directory', () => {
    const target = resolveDbGenerateTarget('app');
    expect(target).toMatchObject({
      packageDir: 'apps/emdash-desktop',
      runScript: 'db:generate:app',
      migrationsDir: 'apps/emdash-desktop/drizzle',
    });
  });

  it('maps each core schema to its packages/core script and migrations directory', () => {
    expect(resolveDbGenerateTarget('automations')).toMatchObject({
      packageDir: 'packages/core',
      runScript: 'db:generate:automations',
      migrationsDir: 'packages/core/src/runtimes/automations/node/persistence/migrations',
    });
    expect(resolveDbGenerateTarget('file-search')).toMatchObject({
      packageDir: 'packages/core',
      runScript: 'db:generate:file-search',
      migrationsDir: 'packages/core/src/runtimes/file-search/node/storage/migrations',
    });
  });

  it('returns undefined for unknown schemas', () => {
    expect(resolveDbGenerateTarget('nope')).toBeUndefined();
  });
});

describe('followUpMessage', () => {
  it('tells app-schema authors to regenerate fixtures and run migration tests', () => {
    const message = followUpMessage('app');
    expect(message).toContain('pnpm run db:fixtures');
    expect(message).toContain('pnpm run test:migrations');
  });

  it('tells core-schema authors to run the core test suite', () => {
    const message = followUpMessage('conversations');
    expect(message).toContain('@emdash/core');
  });
});
