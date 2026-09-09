import { describe, expect, it, vi } from 'vitest';
import { installHostRecoveryWakeups } from './recovery-wakeups';

describe('Host recovery browser wakeups', () => {
  it('forwards online and focus events and releases both listeners', () => {
    const listeners = new Map<string, () => void>();
    const target = {
      addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
        listeners.set(type, listener as () => void);
      },
      removeEventListener(type: string, listener: EventListenerOrEventListenerObject) {
        if (listeners.get(type) === listener) listeners.delete(type);
      },
    };
    const wake = vi.fn();

    const dispose = installHostRecoveryWakeups(target, wake);
    listeners.get('online')?.();
    listeners.get('focus')?.();

    expect(wake.mock.calls).toEqual([['online'], ['focus']]);

    dispose();
    expect(listeners.size).toBe(0);
  });
});
