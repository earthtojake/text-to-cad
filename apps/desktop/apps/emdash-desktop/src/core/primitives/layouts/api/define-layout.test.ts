import type { ComponentType, ReactNode } from 'react';
import { describe, expect, expectTypeOf, it } from 'vitest';
import type { SlotFills } from '@core/primitives/layouts/react';
import { defineLayout, slot } from './define-layout';

describe('defineLayout', () => {
  it('defines a frozen layout with named slot kinds', () => {
    const layout = defineLayout({
      id: 'workbench',
      slots: {
        wrap: slot.wrapper(),
        titlebar: slot.optional(),
        main: slot.main(),
        status: slot.multi(),
      },
    });

    expect(layout.id).toBe('workbench');
    expect(layout.slots).toEqual({
      wrap: { kind: 'wrapper' },
      titlebar: { kind: 'optional' },
      main: { kind: 'main' },
      status: { kind: 'multi' },
    });
    expect(Object.isFrozen(layout)).toBe(true);
    expect(Object.isFrozen(layout.slots)).toBe(true);
  });

  it('rejects an empty layout id', () => {
    expect(() => defineLayout({ id: ' ', slots: { main: slot.main() } })).toThrow(
      'A layout id must not be empty'
    );
  });

  it('derives required, optional, wrapper, and excluded multi-slot fills', () => {
    const layout = defineLayout({
      id: 'workbench',
      slots: {
        wrap: slot.wrapper(),
        titlebar: slot.optional(),
        main: slot.main(),
        status: slot.multi(),
      },
    });

    type Fills = SlotFills<typeof layout, { taskId: string }>;

    expectTypeOf<keyof Fills>().toEqualTypeOf<'wrap' | 'titlebar' | 'main'>();
    expectTypeOf<Fills>().toMatchTypeOf<{
      wrap: ComponentType<{ children: ReactNode; taskId: string }>;
      titlebar?: ComponentType;
      main: ComponentType;
    }>();
  });
});
