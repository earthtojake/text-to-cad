import { describe, expect, it } from 'vitest';
import { deriveMachineStatusKind } from './machine-status-kind';

describe('deriveMachineStatusKind', () => {
  it.each([
    { kind: 'suspended', reason: 'user-disconnected' },
    { kind: 'unavailable', recovery: 'eligible' },
  ] as const)('is idle while runtime readiness is $kind', (availability) => {
    expect(
      deriveMachineStatusKind({
        availability,
      })
    ).toBe('idle');
  });

  it.each(['connecting', 'provisioning', 'handshaking'] as const)(
    'is initializing while Host readiness is %s',
    (phase) => {
      expect(
        deriveMachineStatusKind({
          availability: { kind: 'preparing', phase, attempt: 1 },
        })
      ).toBe('initializing');
    }
  );

  it('is successful only when the runtime is ready', () => {
    expect(
      deriveMachineStatusKind({
        availability: { kind: 'ready', generation: 3 },
      })
    ).toBe('successful');
  });

  it('is an error when runtime readiness reports a semantic issue', () => {
    expect(
      deriveMachineStatusKind({
        availability: {
          kind: 'unavailable',
          recovery: 'manual',
          issue: {
            type: 'host-unavailable',
            host: { type: 'remote', id: 'ssh-1' },
            reason: 'install-failed',
            message: 'Host runtime installation failed',
          },
        },
      })
    ).toBe('error');
  });

  it('is idle until Hosts publishes runtime availability', () => {
    expect(
      deriveMachineStatusKind({
        availability: undefined,
      })
    ).toBe('idle');
  });
});
