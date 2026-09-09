import { useEffect, useRef } from 'react';
import { confirmRegistry, type ConfirmRegistry } from './confirm-registry';

export interface UseConfirmOptions {
  readonly enabled?: boolean;
}

export function useConfirm(
  onConfirm: () => void,
  options: UseConfirmOptions = {},
  registry: ConfirmRegistry = confirmRegistry
): void {
  const onConfirmRef = useRef(onConfirm);
  const enabledRef = useRef(options.enabled ?? true);
  onConfirmRef.current = onConfirm;
  enabledRef.current = options.enabled ?? true;

  useEffect(
    () =>
      registry.register({
        trigger: () => onConfirmRef.current(),
        isEnabled: () => enabledRef.current,
      }),
    [registry]
  );
}
