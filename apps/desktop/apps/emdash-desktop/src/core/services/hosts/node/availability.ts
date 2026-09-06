import { formatHostRef, type HostRef } from '@emdash/core/primitives/host/api';
import {
  runtimeHostUnavailable,
  type RuntimeResolveError,
} from '@emdash/core/primitives/runtime-resolution/api';
import { err, ok, type Result } from '@emdash/shared';
import type { Scope } from '@emdash/shared/concurrency';
import {
  retrySchedules,
  systemClock,
  type Clock,
  type RetrySchedule,
} from '@emdash/shared/scheduling';
import type { LeasedLiveModelProvider } from '@emdash/wire/rpc';
import { cell, expose, peek, type Cell, type Readable } from '@emdash/wire/state';
import { hostsContract } from '../api';
import {
  allowsAutomaticHostRecovery,
  runtimeRecoveryDisposition,
  type BrowserHostWakeCause,
  type ExplicitRecoveryCause,
  type HostAvailability,
  type HostAvailabilityState,
  type HostDemandLease,
  type HostDemandMode,
  type HostPreparingPhase,
  type HostReady,
  type HostWakeCause,
  type RecoveryCause,
} from '../api/availability';

export type HostReadinessContext = {
  readonly signal: AbortSignal;
  readonly cause: RecoveryCause;
  setPhase(phase: HostPreparingPhase): void;
};

export type HostReadinessAdapter = {
  prepare(host: HostRef, context: HostReadinessContext): Promise<Result<void, RuntimeResolveError>>;
};

export type CreateHostAvailabilityOptions = {
  scope: Scope;
  readiness: HostReadinessAdapter;
  clock?: Clock;
  retrySchedule?: RetrySchedule;
};

type ActiveRun = {
  identity: {
    superseded?: RuntimeResolveError;
  };
  scope: Scope;
  cause: RecoveryCause;
  promise: Promise<Result<HostReady, RuntimeResolveError>>;
};

type DemandLeaseState = {
  mode: HostDemandMode;
  released: boolean;
};

type HostDemandEntry = {
  host: HostRef;
  leases: Set<DemandLeaseState>;
};

export class HostAvailabilityService implements HostAvailability {
  readonly host: LeasedLiveModelProvider<typeof hostsContract.availability>;

  private readonly scope: Scope;
  private readonly states = new Map<string, Cell<HostAvailabilityState>>();
  private readonly runs = new Map<string, ActiveRun>();
  private readonly demands = new Map<string, HostDemandEntry>();
  private readonly lastFocusWakeAt = new Map<string, number>();
  private readonly clock: Clock;
  private readonly retrySchedule: RetrySchedule;
  private nextGeneration = 1;

  constructor(private readonly options: CreateHostAvailabilityOptions) {
    this.scope = options.scope.child('host-availability');
    this.clock = options.clock ?? systemClock;
    this.retrySchedule =
      options.retrySchedule ?? retrySchedules.sequence([1_000, 2_000, 5_000, 10_000, 30_000]);
    this.host = expose(hostsContract.availability, {
      state: ({ host }) => this.state(host),
    });
    this.scope.add(() => this.host.dispose());
  }

  state(host: HostRef): Readable<HostAvailabilityState> {
    return this.stateCell(host);
  }

  stateFor(host: HostRef): HostAvailabilityState {
    const state = this.states.get(formatHostRef(host));
    return state ? peek(state) : { kind: 'unavailable', recovery: 'eligible' };
  }

  requireReady(host: HostRef): Result<HostReady, RuntimeResolveError> {
    const state = this.stateFor(host);
    if (state.kind === 'ready') return ok({ host, generation: state.generation });
    if (state.kind === 'unavailable' && state.issue) return err(state.issue);

    switch (state.kind) {
      case 'suspended':
      case 'unavailable':
        return err(runtimeHostUnavailable(host, 'offline', 'Host is offline'));
      case 'preparing':
        return err(
          state.phase === 'connecting'
            ? runtimeHostUnavailable(host, 'connection-failed', 'Host connection is not ready')
            : runtimeHostUnavailable(host, 'runtime-unavailable', 'Host runtime is not ready')
        );
    }
  }

  demand(host: HostRef, mode: HostDemandMode, owner: Scope): HostDemandLease {
    if (owner.disposed) return inactiveDemandLease(mode);
    const key = formatHostRef(host);
    let entry = this.demands.get(key);
    if (!entry) {
      entry = { host, leases: new Set() };
      this.demands.set(key, entry);
    }
    const state: DemandLeaseState = { mode, released: false };
    entry.leases.add(state);
    owner.add(() => this.releaseDemand(key, entry!, state));
    if (mode === 'automatic') void this.ensureReady(host, 'demand');
    return {
      get mode() {
        return state.mode;
      },
      setMode: (nextMode) => {
        if (state.released || state.mode === nextMode) return;
        state.mode = nextMode;
        if (nextMode === 'automatic') {
          void this.ensureReady(host, 'demand');
        } else if (!hasAutomaticDemand(entry)) {
          this.cancelAutomaticRun(host);
        }
      },
    };
  }

  wake(host: HostRef, cause: HostWakeCause): void {
    const key = formatHostRef(host);
    const demand = this.demands.get(key);
    if (!demand || !hasActiveDemand(demand)) return;
    if (cause !== 'ssh-edge' && !hasAutomaticDemand(demand)) return;
    const state = this.stateFor(host);
    if (!allowsRecoveryForCause(state, cause)) return;
    if (cause === 'focus') {
      const lastWakeAt = this.lastFocusWakeAt.get(key);
      if (lastWakeAt !== undefined && this.clock.now() - lastWakeAt < 30_000) return;
      this.lastFocusWakeAt.set(key, this.clock.now());
    }
    void this.ensureReady(host, cause);
  }

  wakeDemanded(cause: BrowserHostWakeCause): void {
    for (const demand of this.demands.values()) {
      this.wake(demand.host, cause);
    }
  }

  ensureReady(
    host: HostRef,
    cause: RecoveryCause
  ): Promise<Result<HostReady, RuntimeResolveError>> {
    const ready = this.requireReady(host);
    if (ready.success) return Promise.resolve(ready);

    const key = formatHostRef(host);
    const existing = this.runs.get(key);
    if (existing) {
      if (!isExplicit(cause) || isExplicit(existing.cause)) return existing.promise;
      this.supersedeRun(
        host,
        existing,
        runtimeHostUnavailable(host, 'runtime-unavailable', 'Host readiness was superseded'),
        'Host readiness superseded'
      );
    }
    if (!isExplicit(cause)) {
      const state = this.stateFor(host);
      if (!allowsRecoveryForCause(state, cause)) {
        return Promise.resolve(ready);
      }
    }

    const runScope = this.scope.child('ready-attempt');
    const identity: ActiveRun['identity'] = {};
    this.setPreparing(host, 1);
    const run = runScope.run('recover', (signal) => this.performRun(host, cause, identity, signal));
    const promise = run
      .value()
      .catch(() => this.commitUnexpectedFailure(host, identity))
      .finally(() => {
        if (this.runs.get(key)?.identity === identity) this.runs.delete(key);
        void runScope.dispose();
      });
    this.runs.set(key, { identity, scope: runScope, cause, promise });
    return promise;
  }

  requestReady(host: HostRef, cause: ExplicitRecoveryCause): void {
    void this.ensureReady(host, cause);
  }

  suspend(host: HostRef): void {
    const key = formatHostRef(host);
    const active = this.runs.get(key);
    if (active) {
      this.supersedeRun(
        host,
        active,
        runtimeHostUnavailable(host, 'offline', 'Host is offline'),
        'Host readiness suspended'
      );
    }
    this.setState(host, { kind: 'suspended', reason: 'user-disconnected' });
  }

  invalidate(host: HostRef, issue?: RuntimeResolveError): void {
    const state = this.stateFor(host);
    if (state.kind === 'suspended') return;
    const key = formatHostRef(host);
    const active = this.runs.get(key);
    if (active && state.kind !== 'ready') return;
    if (active) {
      this.supersedeRun(
        host,
        active,
        issue ?? runtimeHostUnavailable(host, 'offline', 'Host is offline'),
        'Host readiness invalidated'
      );
    }
    this.setState(host, {
      kind: 'unavailable',
      ...(issue ? { issue } : {}),
      recovery: issue ? runtimeRecoveryDisposition(issue) : 'eligible',
    });
    const demand = this.demands.get(key);
    if (demand && hasAutomaticDemand(demand)) {
      void this.ensureReady(host, 'demand');
    }
  }

  /** Temporary alias for pre-availability gateway callers. */
  markUnavailable(host: HostRef, issue?: RuntimeResolveError): void {
    this.invalidate(host, issue);
  }

  private async performRun(
    host: HostRef,
    cause: RecoveryCause,
    identity: ActiveRun['identity'],
    signal: AbortSignal
  ): Promise<Result<HostReady, RuntimeResolveError>> {
    let attempt = 1;
    for (;;) {
      this.setPreparing(host, attempt);
      let result: Result<void, RuntimeResolveError>;
      try {
        result = await this.options.readiness.prepare(host, {
          signal,
          cause,
          setPhase: (phase) => {
            if (this.runs.get(formatHostRef(host))?.identity !== identity) return;
            this.setState(host, { kind: 'preparing', phase, attempt });
          },
        });
      } catch {
        result = err(unexpectedPreparationFailure(host));
      }
      const stale = this.staleRunResult(host, identity);
      if (stale) return stale;
      if (result.success) {
        const generation = this.nextGeneration++;
        this.setState(host, { kind: 'ready', generation });
        return ok({ host, generation });
      }

      const recovery = runtimeRecoveryDisposition(result.error);
      if (recovery !== 'eligible') {
        this.setState(host, {
          kind: 'unavailable',
          issue: result.error,
          recovery,
        });
        return result;
      }
      const delayMs = this.retrySchedule.delayFor(attempt - 1);
      if (delayMs === undefined) {
        this.setState(host, {
          kind: 'unavailable',
          issue: result.error,
          recovery: 'manual',
        });
        return result;
      }
      this.setState(host, {
        kind: 'unavailable',
        issue: result.error,
        recovery: 'waiting',
        nextAttemptAt: this.clock.now() + delayMs,
      });
      await this.clock.sleep(delayMs, { signal });
      attempt += 1;
    }
  }

  private commitUnexpectedFailure(
    host: HostRef,
    identity: ActiveRun['identity']
  ): Result<HostReady, RuntimeResolveError> {
    if (this.runs.get(formatHostRef(host))?.identity !== identity) {
      return err(
        identity.superseded ??
          runtimeHostUnavailable(host, 'runtime-unavailable', 'Host readiness was superseded')
      );
    }
    const error = unexpectedPreparationFailure(host);
    this.setState(host, {
      kind: 'unavailable',
      issue: error,
      recovery: runtimeRecoveryDisposition(error),
    });
    return err(error);
  }

  private staleRunResult(
    host: HostRef,
    identity: ActiveRun['identity']
  ): Result<HostReady, RuntimeResolveError> | undefined {
    if (this.runs.get(formatHostRef(host))?.identity === identity) return undefined;
    return err(
      identity.superseded ??
        runtimeHostUnavailable(host, 'runtime-unavailable', 'Host readiness was superseded')
    );
  }

  private setPreparing(host: HostRef, attempt: number): void {
    this.setState(host, {
      kind: 'preparing',
      phase: host.type === 'local' ? 'handshaking' : 'connecting',
      attempt,
    });
  }

  private stateCell(host: HostRef): Cell<HostAvailabilityState> {
    const key = formatHostRef(host);
    let state = this.states.get(key);
    if (!state) {
      state = cell<HostAvailabilityState>({ kind: 'unavailable', recovery: 'eligible' });
      this.states.set(key, state);
    }
    return state;
  }

  private setState(host: HostRef, state: HostAvailabilityState): void {
    this.stateCell(host).set(state);
  }

  private releaseDemand(key: string, entry: HostDemandEntry, lease: DemandLeaseState): void {
    if (lease.released) return;
    lease.released = true;
    entry.leases.delete(lease);
    if (!hasAutomaticDemand(entry)) this.cancelAutomaticRun(entry.host);
    if (entry.leases.size === 0 && this.demands.get(key) === entry) {
      this.demands.delete(key);
    }
  }

  private cancelAutomaticRun(host: HostRef): void {
    const key = formatHostRef(host);
    const active = this.runs.get(key);
    if (!active || isExplicit(active.cause)) return;
    this.supersedeRun(
      host,
      active,
      runtimeHostUnavailable(
        host,
        'runtime-unavailable',
        'Host readiness no longer has automatic demand'
      ),
      'Host readiness demand released'
    );
    const state = this.stateFor(host);
    if (state.kind === 'preparing') {
      this.setState(host, { kind: 'unavailable', recovery: 'eligible' });
    } else if (state.kind === 'unavailable' && state.recovery === 'waiting') {
      this.setState(host, {
        kind: 'unavailable',
        ...(state.issue ? { issue: state.issue } : {}),
        recovery: 'eligible',
      });
    }
  }

  private supersedeRun(
    host: HostRef,
    active: ActiveRun,
    result: RuntimeResolveError,
    reason: string
  ): void {
    active.identity.superseded = result;
    if (this.runs.get(formatHostRef(host))?.identity === active.identity) {
      this.runs.delete(formatHostRef(host));
    }
    void active.scope.dispose(new Error(reason));
  }
}

export function createHostAvailability(
  options: CreateHostAvailabilityOptions
): HostAvailabilityService {
  return new HostAvailabilityService(options);
}

function isExplicit(cause: RecoveryCause): boolean {
  return cause === 'connect' || cause === 'retry';
}

function allowsRecoveryForCause(state: HostAvailabilityState, cause: RecoveryCause): boolean {
  if (state.kind === 'suspended') return false;
  return cause === 'ssh-edge' || allowsAutomaticHostRecovery(state);
}

function unexpectedPreparationFailure(host: HostRef): RuntimeResolveError {
  return runtimeHostUnavailable(host, 'runtime-unavailable', 'Host runtime preparation failed');
}

function inactiveDemandLease(mode: HostDemandMode): HostDemandLease {
  return {
    mode,
    setMode() {},
  };
}

function hasAutomaticDemand(entry: HostDemandEntry): boolean {
  for (const lease of entry.leases) {
    if (!lease.released && lease.mode === 'automatic') return true;
  }
  return false;
}

function hasActiveDemand(entry: HostDemandEntry): boolean {
  for (const lease of entry.leases) {
    if (!lease.released) return true;
  }
  return false;
}
