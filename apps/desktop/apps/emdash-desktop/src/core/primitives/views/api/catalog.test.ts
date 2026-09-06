import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { defineLayout, slot } from '@core/primitives/layouts/api';
import { defineViewCatalog } from './catalog';
import { defineView } from './define-view';

const layout = defineLayout({
  id: 'test',
  slots: { main: slot.main() },
});

describe('defineViewCatalog', () => {
  it('preserves the definition tuple and looks up views by id', () => {
    const homeView = defineView({
      id: 'home',
      params: z.object({}),
      layout,
    });
    const taskView = defineView({
      id: 'task',
      params: z.object({ taskId: z.string() }),
      layout,
    });
    const catalog = defineViewCatalog([homeView, taskView] as const);

    expect(catalog.defs).toEqual([homeView, taskView]);
    expect(catalog.byId('task')).toBe(taskView);
    expect(catalog.byId('missing')).toBeUndefined();
    expect(Object.isFrozen(catalog)).toBe(true);
    expect(Object.isFrozen(catalog.defs)).toBe(true);
    expectTypeOf<(typeof catalog.defs)[number]['id']>().toEqualTypeOf<'home' | 'task'>();
  });

  it('rejects duplicate view ids', () => {
    const first = defineView({
      id: 'home',
      params: z.object({}),
      layout,
    });
    const duplicate = defineView({
      id: 'home',
      params: z.object({ tab: z.string().optional() }),
      layout,
    });

    expect(() => defineViewCatalog([first, duplicate])).toThrow('Duplicate view id: home');
  });
});
