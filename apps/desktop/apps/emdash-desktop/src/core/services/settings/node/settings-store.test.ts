import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import {
  appSettingsContributions,
  getDefaultForKey,
} from '@core/manifests/node/settings-contributions';
import {
  AppSettingsKeys,
  type AppSettings,
  type AppSettingsKey,
} from '@core/manifests/shared/settings-contributions';
import {
  defineSettingsContribution,
  type SettingsContributionMap,
} from '@core/primitives/settings/api';

const rows = vi.hoisted(() => new Map<string, string>());

vi.mock('drizzle-orm', () => ({
  eq: vi.fn((column, value) => ({ column, value })),
}));

vi.mock('@core/services/app-db/node/schema', () => ({
  appSettings: { key: 'key', value: 'value' },
}));

const db = {
  select: vi.fn(() => ({
    from: vi.fn(() => ({
      where: vi.fn((predicate: { value: string }) => ({
        execute: vi.fn(async () => {
          const value = rows.get(predicate.value);
          return value === undefined ? [] : [{ key: predicate.value, value }];
        }),
      })),
    })),
  })),
  insert: vi.fn(() => ({
    values: vi.fn((row: { key: string; value: string }) => ({
      onConflictDoUpdate: vi.fn(() => ({
        execute: vi.fn(async () => {
          rows.set(row.key, row.value);
        }),
      })),
    })),
  })),
  delete: vi.fn(() => ({
    where: vi.fn((predicate: { value: string }) => ({
      execute: vi.fn(async () => {
        rows.delete(predicate.value);
      }),
    })),
  })),
} as never;

const { SettingsStore } = await import('./settings-store');

async function roundTripDefault<K extends AppSettingsKey>(key: K): Promise<void> {
  const settings = new SettingsStore(db, appSettingsContributions);
  const value = getDefaultForKey(key);
  await settings.update(key, value);
  expect(await settings.get(key)).toEqual(value);
}

describe('SettingsStore contributions', () => {
  for (const key of AppSettingsKeys) {
    it(`round-trips the ${key} contribution defaults`, async () => {
      rows.clear();
      await roundTripDefault(key);
    });
  }

  it('adopts legacy object deltas and preserves unversioned delta writes', async () => {
    rows.set('tasks', JSON.stringify({ autoGenerateName: false }));
    const settings = new SettingsStore(db, appSettingsContributions);

    expect(await settings.get('tasks')).toEqual({
      ...getDefaultForKey('tasks'),
      autoGenerateName: false,
    });

    const value: AppSettings['tasks'] = {
      ...getDefaultForKey('tasks'),
      autoApproveByDefault: true,
    };
    await settings.update('tasks', value);
    expect(JSON.parse(rows.get('tasks')!)).toEqual({ autoApproveByDefault: true });
  });

  it('adopts legacy scalar values', async () => {
    rows.set('theme', JSON.stringify('emdark'));
    const settings = new SettingsStore(db, appSettingsContributions);
    await expect(settings.get('theme')).resolves.toBe('emdark');
  });

  it('treats a single value field as a setting delta, not a storage envelope', async () => {
    const valueContribution = defineSettingsContribution({
      key: 'browserPreview',
      schema: z.object({ value: z.string() }),
      defaults: { value: 'default' },
    });
    const contributions = {
      ...appSettingsContributions,
      browserPreview: valueContribution,
    } as unknown as SettingsContributionMap<AppSettings>;
    rows.set('browserPreview', JSON.stringify({ value: 'custom' }));

    const settings = new SettingsStore(db, contributions);

    await expect(settings.get('browserPreview')).resolves.toEqual({ value: 'custom' });
  });

  it('reports scalar overrides without returning the scalar as an overrides object', async () => {
    rows.set('theme', JSON.stringify('emdark'));
    const settings = new SettingsStore(db, appSettingsContributions);

    await expect(settings.getWithMeta('theme')).resolves.toEqual({
      value: 'emdark',
      defaults: null,
      overrides: {},
    });
  });
});
