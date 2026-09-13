import { createContext, useContext, type PropsWithChildren, type ReactElement } from 'react';

export interface ModalHostController {
  complete(result: unknown): void;
  dismiss(): void;
  setCloseGuard(active: boolean): void;
  readonly hasActiveCloseGuard: boolean;
}

export interface ModalHostValue {
  readonly id: string;
  readonly controller: ModalHostController;
}

export const ModalHostContext = createContext<ModalHostValue | undefined>(undefined);

export function assertModalHost(
  host: ModalHostValue | undefined,
  expectedId: string
): ModalHostController {
  if (!host) {
    throw new Error('useModalController must be used inside a modal host');
  }
  if (host.id !== expectedId) {
    throw new Error(`Active modal is '${host.id}', not '${expectedId}'`);
  }
  return host.controller;
}

export function useModalHostController(id: string): ModalHostController {
  return assertModalHost(useContext(ModalHostContext), id);
}

export function ModalHostTestProvider({
  children,
  id,
  controller,
}: PropsWithChildren<{
  readonly id: string;
  readonly controller: ModalHostController;
}>): ReactElement {
  return (
    <ModalHostContext.Provider value={{ id, controller }}>{children}</ModalHostContext.Provider>
  );
}
