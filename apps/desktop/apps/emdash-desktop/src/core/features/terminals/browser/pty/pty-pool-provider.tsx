import { useEffect, type ReactNode } from 'react';
import { disposeAllPtys } from '@core/features/terminals/api/browser/pty/pty';
import { ensureXtermHost } from './xterm-host';

export function TerminalPoolProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    ensureXtermHost();
    return () => {
      disposeAllPtys();
    };
  }, []);

  return <>{children}</>;
}
