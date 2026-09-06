import { describe, expect, it, vi } from 'vitest';
import z from 'zod';

const store = vi.hoisted(() => new Map<string, string>());

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
          const value = store.get(predicate.value);
          return value === undefined ? [] : [{ key: predicate.value, value }];
        }),
      })),
    })),
  })),
  insert: vi.fn(() => ({
    values: vi.fn((row: { key: string; value: string }) => ({
      onConflictDoUpdate: vi.fn(() => ({
        execute: vi.fn(async () => {
          store.set(row.key, row.value);
        }),
      })),
    })),
  })),
  delete: vi.fn(() => ({
    where: vi.fn((predicate: { value: string }) => ({
      execute: vi.fn(async () => {
        store.delete(predicate.value);
      }),
    })),
  })),
} as never;

const { OverrideSettings } = await import('./override-settings');

describe('OverrideSettings', () => {
  it('returns metadata for items that have overrides but no defaults entry', async () => {
    store.clear();
    const settings = new OverrideSettings(
      db,
      'providerConfigs',
      () => ({}),
      z.object({ extraArgs: z.string().optional() })
    );

    await settings.updateItem('claude', { extraArgs: '--verbose' });

    expect(await settings.getItemWithMeta('claude')).toEqual({
      value: { extraArgs: '--verbose' },
      defaults: {},
      overrides: { extraArgs: '--verbose' },
    });
  });

  it('returns empty metadata for items with neither defaults nor overrides', async () => {
    store.clear();
    const settings = new OverrideSettings(
      db,
      'providerConfigs',
      () => ({}),
      z.object({ extraArgs: z.string().optional() })
    );

    expect(await settings.getItemWithMeta('claude')).toEqual({
      value: {},
      defaults: {},
      overrides: {},
    });
  });
});
