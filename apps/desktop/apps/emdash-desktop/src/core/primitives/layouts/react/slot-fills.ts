import type { ComponentType, ReactNode } from 'react';
import type { LayoutDef, SlotSpec } from '@core/primitives/layouts/api';

export type SlotFill<TSpec extends SlotSpec, TParams extends object> =
  TSpec extends SlotSpec<'wrapper'>
    ? ComponentType<{ children: ReactNode } & TParams>
    : ComponentType;

type RequiredSlotKeys<TSlots extends Record<string, SlotSpec>> = {
  [TKey in keyof TSlots]: TSlots[TKey]['kind'] extends 'main' | 'wrapper' ? TKey : never;
}[keyof TSlots];

type OptionalSlotKeys<TSlots extends Record<string, SlotSpec>> = {
  [TKey in keyof TSlots]: TSlots[TKey]['kind'] extends 'optional' ? TKey : never;
}[keyof TSlots];

export type SlotFills<TLayout extends LayoutDef, TParams extends object> = {
  [TKey in RequiredSlotKeys<TLayout['slots']>]: SlotFill<TLayout['slots'][TKey], TParams>;
} & {
  [TKey in OptionalSlotKeys<TLayout['slots']>]?: SlotFill<TLayout['slots'][TKey], TParams>;
};
