declare const layoutBrand: unique symbol;

export type SlotKind = 'main' | 'optional' | 'wrapper' | 'multi';

export interface SlotSpec<TKind extends SlotKind = SlotKind> {
  readonly kind: TKind;
}

function defineSlot<TKind extends SlotKind>(kind: TKind): SlotSpec<TKind> {
  return Object.freeze({ kind });
}

export const slot = Object.freeze({
  main: (): SlotSpec<'main'> => defineSlot('main'),
  optional: (): SlotSpec<'optional'> => defineSlot('optional'),
  wrapper: (): SlotSpec<'wrapper'> => defineSlot('wrapper'),
  multi: (): SlotSpec<'multi'> => defineSlot('multi'),
});

export interface LayoutDef<
  TId extends string = string,
  TSlots extends Record<string, SlotSpec> = Record<string, SlotSpec>,
> {
  readonly id: TId;
  readonly slots: TSlots;
  readonly [layoutBrand]: TId;
}

export interface DefineLayoutOptions<TId extends string, TSlots extends Record<string, SlotSpec>> {
  readonly id: TId;
  readonly slots: TSlots;
}

export function defineLayout<
  const TId extends string,
  const TSlots extends Record<string, SlotSpec>,
>(options: DefineLayoutOptions<TId, TSlots>): LayoutDef<TId, TSlots> {
  if (options.id.trim().length === 0) {
    throw new Error('A layout id must not be empty');
  }

  return Object.freeze({
    id: options.id,
    slots: Object.freeze({ ...options.slots }),
  }) as unknown as LayoutDef<TId, TSlots>;
}
