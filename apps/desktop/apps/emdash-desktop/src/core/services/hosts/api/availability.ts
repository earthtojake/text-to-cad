import { hostRefSchema, type HostRef } from '@emdash/core/primitives/host/api';
import {
  runtimeResolveErrorSchema,
  type RuntimeResolveError,
} from '@emdash/core/primitives/runtime-resolution/api';
import type { Result } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import type { Readable } from '@emdash/wire/state';
import { z } from 'zod';

export const hostAvailabilityStateSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('unavailable'),
    issue: runtimeResolveErrorSchema.optional(),
    recovery: z.enum(['eligible', 'waiting', 'manual', 'blocked']),
    nextAttemptAt: z.number().optional(),
  }),
  z.object({
    kind: z.literal('preparing'),
    phase: z.enum(['connecting', 'provisioning', 'handshaking']),
    attempt: z.number().int().positive(),
  }),
  z.object({
    kind: z.literal('ready'),
    generation: z.number().int().positive(),
  }),
  z.object({
    kind: z.literal('suspended'),
    reason: z.literal('user-disconnected'),
  }),
]);

export const hostReadySchema = z.object({
  host: hostRefSchema,
  generation: z.number().int().positive(),
});

export type HostAvailabilityState = z.output<typeof hostAvailabilityStateSchema>;
export type HostReady = z.output<typeof hostReadySchema>;
export type HostPreparingPhase = Extract<HostAvailabilityState, { kind: 'preparing' }>['phase'];
export type RecoveryCause = 'demand' | 'connect' | 'retry' | 'ssh-edge' | 'online' | 'focus';
export type ExplicitRecoveryCause = Extract<RecoveryCause, 'connect' | 'retry'>;
export type HostDemandMode = 'automatic' | 'passive';
export type HostWakeCause = Extract<RecoveryCause, 'ssh-edge' | 'online' | 'focus'>;
export type BrowserHostWakeCause = Extract<HostWakeCause, 'online' | 'focus'>;

export interface HostDemandLease {
  readonly mode: HostDemandMode;
  setMode(mode: HostDemandMode): void;
}

export interface HostAvailability {
  state(host: HostRef): Readable<HostAvailabilityState>;
  stateFor(host: HostRef): HostAvailabilityState;
  requireReady(host: HostRef): Result<HostReady, RuntimeResolveError>;
  demand(host: HostRef, mode: HostDemandMode, owner: Scope): HostDemandLease;
  wake(host: HostRef, cause: HostWakeCause): void;
  wakeDemanded(cause: BrowserHostWakeCause): void;
  ensureReady(host: HostRef, cause: RecoveryCause): Promise<Result<HostReady, RuntimeResolveError>>;
  requestReady(host: HostRef, cause: ExplicitRecoveryCause): void;
  invalidate(host: HostRef, issue?: RuntimeResolveError): void;
  suspend(host: HostRef): void;
}

export function runtimeRecoveryDisposition(
  error: RuntimeResolveError
): Extract<HostAvailabilityState, { kind: 'unavailable' }>['recovery'] {
  if (error.type !== 'host-unavailable') return 'blocked';
  switch (error.reason) {
    case 'offline':
    case 'connection-failed':
    case 'daemon-start-failed':
    case 'runtime-unavailable':
      return 'eligible';
    case 'artifact-download-failed':
    case 'install-failed':
      return 'manual';
    case 'unsupported-platform':
    case 'protocol-upgrade-client':
    case 'protocol-upgrade-server':
      return 'blocked';
  }
}

export function allowsAutomaticHostRecovery(state: HostAvailabilityState): boolean {
  return (
    state.kind !== 'suspended' &&
    (state.kind !== 'unavailable' || (state.recovery !== 'manual' && state.recovery !== 'blocked'))
  );
}
