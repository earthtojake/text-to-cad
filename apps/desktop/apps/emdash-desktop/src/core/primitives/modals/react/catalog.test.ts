import { describe, expect, expectTypeOf, it } from 'vitest';
import { defineModalCatalog, type ModalIdOf } from './catalog';
import { defineModal } from './define-modal';

function EmptyModal() {
  return null;
}

describe('defineModalCatalog', () => {
  it('preserves the definition tuple and looks up modals by id', () => {
    const first = defineModal()({ id: 'first', component: EmptyModal });
    const second = defineModal()({ id: 'second', component: EmptyModal });
    const catalog = defineModalCatalog([first, second] as const);

    expect(catalog.defs).toEqual([first, second]);
    expect(catalog.byId('second')).toBe(second);
    expect(catalog.byId('missing')).toBeUndefined();
    expect(Object.isFrozen(catalog)).toBe(true);
    expect(Object.isFrozen(catalog.defs)).toBe(true);
    expectTypeOf<ModalIdOf<typeof catalog>>().toEqualTypeOf<'first' | 'second'>();
  });

  it('rejects duplicate modal ids', () => {
    const first = defineModal()({ id: 'duplicate', component: EmptyModal });
    const second = defineModal()({ id: 'duplicate', component: EmptyModal });

    expect(() => defineModalCatalog([first, second])).toThrow('Duplicate modal id: duplicate');
  });
});
