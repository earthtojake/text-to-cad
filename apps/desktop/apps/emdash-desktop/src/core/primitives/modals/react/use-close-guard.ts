import { useContext, useEffect } from 'react';
import { ModalHostContext } from '@core/primitives/modals/react';

/**
 * Activates a close guard on the currently open modal while `isActive` is true,
 * preventing it from being dismissed via escape key or clicking outside.
 * Does not block explicit close button clicks.
 */
export function useCloseGuard(isActive: boolean) {
  const host = useContext(ModalHostContext);
  if (!host) {
    throw new Error('useCloseGuard must be used inside a modal host');
  }
  const { setCloseGuard } = host.controller;

  useEffect(() => {
    setCloseGuard(isActive);
    return () => {
      if (isActive) setCloseGuard(false);
    };
  }, [isActive, setCloseGuard]);
}
