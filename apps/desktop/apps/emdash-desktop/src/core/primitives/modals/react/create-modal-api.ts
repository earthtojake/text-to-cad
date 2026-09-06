import type { Result } from '@emdash/shared';
import { useCallback } from 'react';
import { type AnyModalCatalog, type ModalById, type ModalIdOf } from './catalog';
import {
  type ModalDismissed,
  type ModalPropsArgs,
  type ModalResultArgs,
  type ModalResultOf,
} from './define-modal';
import { useModalHostController } from './host-context';

export interface ModalApiTransport {
  open(id: string, props: unknown): Promise<Result<unknown, ModalDismissed>>;
}

export interface ModalController<
  TCatalog extends AnyModalCatalog,
  TId extends ModalIdOf<TCatalog>,
> {
  complete(...args: ModalResultArgs<ModalResultOf<ModalById<TCatalog>[TId]>>): void;
  dismiss(): void;
  setCloseGuard(active: boolean): void;
  readonly hasActiveCloseGuard: boolean;
}

export interface ModalApi<TCatalog extends AnyModalCatalog> {
  openModal<TId extends ModalIdOf<TCatalog>>(
    id: TId,
    ...props: ModalPropsArgs<ModalById<TCatalog>[TId]>
  ): Promise<Result<ModalResultOf<ModalById<TCatalog>[TId]>, ModalDismissed>>;
  useOpenModal<TId extends ModalIdOf<TCatalog>>(
    id: TId
  ): (
    ...props: ModalPropsArgs<ModalById<TCatalog>[TId]>
  ) => Promise<Result<ModalResultOf<ModalById<TCatalog>[TId]>, ModalDismissed>>;
  useModalController<TId extends ModalIdOf<TCatalog>>(id: TId): ModalController<TCatalog, TId>;
}

const unavailableTransport: ModalApiTransport = {
  open(id): never {
    throw new Error(`Modal API is not connected; cannot open '${id}'`);
  },
};

export function createModalApi<TCatalog extends AnyModalCatalog>(
  transport: ModalApiTransport = unavailableTransport
): ModalApi<TCatalog> {
  const openModal = ((id: string, ...props: [props?: unknown]) =>
    transport.open(id, props[0] ?? {})) as ModalApi<TCatalog>['openModal'];

  const useOpenModal = ((id: string) =>
    useCallback(
      (...props: [props?: unknown]) => transport.open(id, props[0] ?? {}),
      [id]
    )) as ModalApi<TCatalog>['useOpenModal'];

  const useModalController = ((id: string) => {
    const controller = useModalHostController(id);
    return {
      complete: (...args: [result?: unknown]) => controller.complete(args[0]),
      dismiss: controller.dismiss,
      setCloseGuard: controller.setCloseGuard,
      hasActiveCloseGuard: controller.hasActiveCloseGuard,
    };
  }) as ModalApi<TCatalog>['useModalController'];

  return Object.freeze({ openModal, useOpenModal, useModalController });
}
