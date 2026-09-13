import { describe, expect, expectTypeOf, it } from 'vitest';
import {
  defineModal,
  type ModalPropsArgs,
  type ModalPropsOf,
  type ModalResultOf,
} from './define-modal';

function RequiredModal(_props: { name: string }) {
  return null;
}

function OptionalModal(_props: { tab?: string }) {
  return null;
}

describe('defineModal', () => {
  it('creates a frozen definition and infers props from the component', () => {
    const modal = defineModal<'accepted' | 'rejected'>()({
      id: 'decisionModal',
      component: RequiredModal,
      size: 'sm',
    });

    expect(modal).toMatchObject({
      id: 'decisionModal',
      component: RequiredModal,
      size: 'sm',
    });
    expect(Object.isFrozen(modal)).toBe(true);
    expectTypeOf<ModalPropsOf<typeof modal>>().toEqualTypeOf<{ name: string }>();
    expectTypeOf<ModalResultOf<typeof modal>>().toEqualTypeOf<'accepted' | 'rejected'>();
  });

  it('makes props optional only when every field is optional', () => {
    const requiredModal = defineModal()({
      id: 'requiredModal',
      component: RequiredModal,
    });
    const optionalModal = defineModal()({
      id: 'optionalModal',
      component: OptionalModal,
    });

    expectTypeOf<ModalPropsArgs<typeof requiredModal>>().toEqualTypeOf<[props: { name: string }]>();
    expectTypeOf<ModalPropsArgs<typeof optionalModal>>().toEqualTypeOf<
      [props?: { tab?: string }]
    >();
  });

  it('rejects an empty modal id', () => {
    expect(() =>
      defineModal()({
        id: ' ',
        component: RequiredModal,
      })
    ).toThrow('A modal id must not be empty');
  });
});
