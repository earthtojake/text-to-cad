import type { ComponentType } from 'react';

declare const modalBrand: unique symbol;

export type ModalSize = 'xs' | 'sm' | 'md' | 'lg';
export type ModalPosition = 'center' | 'top';

interface ModalTypes<TResult> {
  readonly result: TResult;
}

export interface ModalDef<
  TId extends string = string,
  TComponent extends ComponentType<never> = ComponentType<never>,
  TResult = void,
> {
  readonly id: TId;
  readonly component: TComponent;
  readonly size?: ModalSize;
  readonly position?: ModalPosition;
  readonly ignoreOutsidePressAfterWindowBlur?: boolean;
  readonly [modalBrand]?: ModalTypes<TResult>;
}

export interface DefineModalOptions<TId extends string, TComponent extends ComponentType<never>> {
  readonly id: TId;
  readonly component: TComponent;
  readonly size?: ModalSize;
  readonly position?: ModalPosition;
  readonly ignoreOutsidePressAfterWindowBlur?: boolean;
}

export function defineModal<TResult = void>() {
  return <const TId extends string, TComponent extends ComponentType<never>>(
    options: DefineModalOptions<TId, TComponent>
  ): ModalDef<TId, TComponent, TResult> => {
    if (options.id.trim().length === 0) {
      throw new Error('A modal id must not be empty');
    }
    return Object.freeze({ ...options }) as ModalDef<TId, TComponent, TResult>;
  };
}

export type ModalPropsOf<TDef> = TDef extends {
  readonly component: ComponentType<infer TProps>;
}
  ? TProps
  : never;

export type ModalResultOf<TDef> = TDef extends {
  readonly [modalBrand]?: ModalTypes<infer TResult>;
}
  ? TResult
  : never;

export type ModalPropsArgs<TDef> =
  Record<string, never> extends ModalPropsOf<TDef>
    ? [props?: ModalPropsOf<TDef>]
    : [props: ModalPropsOf<TDef>];

export type ModalResultArgs<TResult> = [TResult] extends [void]
  ? [result?: TResult]
  : [result: TResult];

export type ModalDismissReason = 'explicit' | 'passive' | 'navigation';

export type ModalDismissed = {
  readonly type: 'modal_dismissed';
  readonly reason: ModalDismissReason;
};
