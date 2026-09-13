import { useEffect } from 'react';
import type { BrowserHostWakeCause } from '../api/availability';
import { getHostsClient } from '../api/client';

type BrowserWakeTarget = {
  addEventListener(type: 'online' | 'focus', listener: () => void): void;
  removeEventListener(type: 'online' | 'focus', listener: () => void): void;
};

export function installHostRecoveryWakeups(
  target: BrowserWakeTarget,
  wake: (cause: BrowserHostWakeCause) => void
): () => void {
  const online = () => wake('online');
  const focus = () => wake('focus');
  target.addEventListener('online', online);
  target.addEventListener('focus', focus);
  return () => {
    target.removeEventListener('focus', focus);
    target.removeEventListener('online', online);
  };
}

export function HostRecoveryWakeups() {
  useEffect(
    () =>
      installHostRecoveryWakeups(window, (cause) => {
        void getHostsClient().then((client) => client.wake({ cause }));
      }),
    []
  );
  return null;
}
