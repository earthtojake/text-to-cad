import type { Result, Unsubscribe } from '@emdash/shared';
import { ok } from '@emdash/shared';
import type {
  AcpPermissionRequest,
  AcpRuntimeError,
  PromptInput,
  QueuedPrompt,
  SessionLifecycle,
  SessionState,
  StopReason,
} from '#runtimes/acp/api';
import { acpErr, makeTurnId } from '#runtimes/acp/api';
import { createMachine, type Machine, type MachineBatch } from './primitive';

export type SessionPhase =
  | { kind: 'starting' }
  | { kind: 'replaying'; turn: ControlTurn }
  | { kind: 'ready' }
  | { kind: 'working'; turn: ControlTurn }
  | { kind: 'cancelling'; turn: ControlTurn }
  | { kind: 'closed'; exitCode: number | null };

export interface ControlTurn {
  id: string;
}

export interface SessionMachineContext {
  modeIds?: readonly string[];
  configOptionIds?: readonly string[];
}

export function emptySessionMachineContext(): SessionMachineContext {
  return { modeIds: [], configOptionIds: [] };
}

export function phaseToLifecycle(phase: SessionPhase): SessionLifecycle {
  return phase.kind;
}

export function activeTurnFromPhase(phase: SessionPhase): ControlTurn | null {
  if (phase.kind === 'replaying' || phase.kind === 'working' || phase.kind === 'cancelling') {
    return phase.turn;
  }
  return null;
}

export interface SessionMachineState {
  readonly conversationId: string;
  readonly phase: SessionPhase;
  readonly pendingPermissions: readonly AcpPermissionRequest[];
  readonly lastStopReason: StopReason | null;
  readonly lastTurnErrored: boolean;
  readonly nextTurnIndex: number;
  readonly queuedPrompts: readonly QueuedPrompt[];
  readonly agentTurnActive: boolean;
  readonly backgroundAgentCount: number;
}

export function initialMachineState(conversationId: string): SessionMachineState {
  return {
    conversationId,
    phase: { kind: 'starting' },
    pendingPermissions: [],
    lastStopReason: null,
    lastTurnErrored: false,
    nextTurnIndex: 0,
    queuedPrompts: [],
    agentTurnActive: false,
    backgroundAgentCount: 0,
  };
}

export type Command =
  | { type: 'Prompt'; prompt: QueuedPrompt }
  | { type: 'QueuePrompt'; prompt: QueuedPrompt }
  | { type: 'Cancel' }
  | { type: 'EditQueuedPrompt'; id: string; input: PromptInput; updatedAt: number }
  | { type: 'RemoveQueuedPrompt'; id: string }
  | { type: 'ReorderQueue'; ids: readonly string[] }
  | { type: 'ResolvePermission'; requestId: string; optionId: string }
  | { type: 'SetMode'; modeId: string }
  | { type: 'SetConfigOption'; configId: string; value: string };

export type DomainEvent =
  | { type: 'ReplayStarted' }
  | { type: 'ReplayEnded'; status: 'complete' | 'error' | 'cancelled' }
  | { type: 'SessionReady' }
  | { type: 'SessionLoaded' }
  | { type: 'PromptStarted'; prompt: QueuedPrompt }
  | { type: 'PromptQueued'; prompt: QueuedPrompt }
  | { type: 'QueuedPromptEdited'; id: string; input: PromptInput; updatedAt: number }
  | { type: 'QueuedPromptRemoved'; id: string }
  | { type: 'QueueReordered'; ids: readonly string[] }
  | { type: 'TurnEnded'; outcome: TurnOutcome }
  | { type: 'AgentActivity'; active: boolean }
  | { type: 'AgentsChanged'; runningCount: number }
  | { type: 'CancellationRequested' }
  | { type: 'PermissionRequested'; request: AcpPermissionRequest }
  | { type: 'PermissionResolved'; requestId: string }
  | { type: 'ProcessClosed'; exitCode: number | null };

export type TurnOutcome = { kind: 'stopped'; stopReason: StopReason } | { kind: 'errored' };

export type Effect =
  | { type: 'state' }
  | { type: 'permissionRequest'; request: AcpPermissionRequest }
  | { type: 'permissionResolved'; requestId: string; cancelled: boolean }
  | { type: 'closed'; exitCode: number | null }
  | { type: 'agentEvent'; phase: 'start' | 'stop' | 'error' }
  | { type: 'settleAgents'; scope: 'turn' | 'all'; status: 'completed' | 'failed' }
  | { type: 'sendPrompt'; prompt: QueuedPrompt }
  | { type: 'warn'; message: string };

export function decide(
  s: SessionMachineState,
  cmd: Command,
  ctx: SessionMachineContext = emptySessionMachineContext()
): Result<DomainEvent[], AcpRuntimeError> {
  switch (cmd.type) {
    case 'Prompt':
      if (
        s.phase.kind === 'working' ||
        s.phase.kind === 'cancelling' ||
        s.agentTurnActive ||
        s.backgroundAgentCount > 0
      ) {
        return ok([{ type: 'PromptQueued', prompt: cmd.prompt }]);
      }
      if (!isPromptReady(phaseToLifecycle(s.phase))) {
        return acpErr.invalidState(`Cannot send a prompt while session is '${s.phase.kind}'`);
      }
      return ok([{ type: 'PromptStarted', prompt: cmd.prompt }]);

    case 'QueuePrompt':
      return ok([{ type: 'PromptQueued', prompt: cmd.prompt }]);

    case 'Cancel':
      if (s.phase.kind !== 'working' && !s.agentTurnActive && s.backgroundAgentCount === 0) {
        return ok([]);
      }
      return ok([{ type: 'CancellationRequested' }]);

    case 'EditQueuedPrompt':
      if (!s.queuedPrompts.some((prompt) => prompt.id === cmd.id)) return ok([]);
      return ok([
        { type: 'QueuedPromptEdited', id: cmd.id, input: cmd.input, updatedAt: cmd.updatedAt },
      ]);

    case 'RemoveQueuedPrompt':
      if (!s.queuedPrompts.some((prompt) => prompt.id === cmd.id)) return ok([]);
      return ok([{ type: 'QueuedPromptRemoved', id: cmd.id }]);

    case 'ReorderQueue': {
      const knownIds = new Set(s.queuedPrompts.map((prompt) => prompt.id));
      if (cmd.ids.length !== knownIds.size || cmd.ids.some((id) => !knownIds.has(id))) {
        return acpErr.invalidState('Queue reorder ids must match the queued prompts');
      }
      return ok([{ type: 'QueueReordered', ids: cmd.ids }]);
    }

    case 'ResolvePermission':
      if (!s.pendingPermissions.some((p) => p.requestId === cmd.requestId)) {
        return acpErr.invalidState(`No pending permission request with id '${cmd.requestId}'`);
      }
      return ok([{ type: 'PermissionResolved', requestId: cmd.requestId }]);

    case 'SetMode':
      if (!ctx.modeIds?.includes(cmd.modeId)) {
        return acpErr.setModeFailed({
          name: 'Error',
          message: `Mode '${cmd.modeId}' is not in the available modes list`,
        });
      }
      return ok([]);

    case 'SetConfigOption':
      if (!ctx.configOptionIds?.includes(cmd.configId)) {
        return acpErr.setConfigFailed({
          name: 'Error',
          message: `Config option '${cmd.configId}' is not known`,
        });
      }
      return ok([]);
  }
}

export function evolve(
  s: SessionMachineState,
  ev: DomainEvent
): { state: SessionMachineState; effects: Effect[] } {
  switch (ev.type) {
    case 'ReplayStarted': {
      if (s.phase.kind !== 'starting') return warn(s, `ReplayStarted in phase '${s.phase.kind}'`);
      const turn = makeTurn(s);
      return {
        state: { ...s, phase: { kind: 'replaying', turn }, nextTurnIndex: s.nextTurnIndex + 1 },
        effects: [{ type: 'state' }],
      };
    }

    case 'ReplayEnded': {
      if (s.phase.kind !== 'replaying') return warn(s, `ReplayEnded in phase '${s.phase.kind}'`);
      const { queuedPrompts, effects: queueEffects } = dequeuePromptEffects(s.queuedPrompts);
      return {
        state: { ...s, phase: { kind: 'ready' }, queuedPrompts },
        effects: [
          { type: 'state' },
          { type: 'settleAgents', scope: 'turn', status: 'completed' },
          ...queueEffects,
        ],
      };
    }

    case 'SessionReady': {
      if (s.phase.kind !== 'starting') return warn(s, `SessionReady in phase '${s.phase.kind}'`);
      const { queuedPrompts, effects: queueEffects } = dequeuePromptEffects(s.queuedPrompts);
      return {
        state: { ...s, phase: { kind: 'ready' }, queuedPrompts },
        effects: [{ type: 'state' }, ...queueEffects],
      };
    }

    case 'SessionLoaded':
      if (s.phase.kind !== 'replaying') return warn(s, `SessionLoaded in phase '${s.phase.kind}'`);
      return { state: s, effects: [] };

    case 'PromptStarted': {
      if (s.phase.kind !== 'ready') return warn(s, `PromptStarted in phase '${s.phase.kind}'`);
      const turn = makeTurn(s);
      return {
        state: {
          ...s,
          phase: { kind: 'working', turn },
          nextTurnIndex: s.nextTurnIndex + 1,
          agentTurnActive: false,
        },
        effects: [{ type: 'state' }, { type: 'agentEvent', phase: 'start' }],
      };
    }

    case 'PromptQueued':
      return {
        state: { ...s, queuedPrompts: [...s.queuedPrompts, ev.prompt] },
        effects: [{ type: 'state' }],
      };

    case 'QueuedPromptEdited':
      return {
        state: {
          ...s,
          queuedPrompts: s.queuedPrompts.map((prompt) =>
            prompt.id === ev.id ? { ...prompt, ...ev.input, updatedAt: ev.updatedAt } : prompt
          ),
        },
        effects: [{ type: 'state' }],
      };

    case 'QueuedPromptRemoved':
      return {
        state: {
          ...s,
          queuedPrompts: s.queuedPrompts.filter((prompt) => prompt.id !== ev.id),
        },
        effects: [{ type: 'state' }],
      };

    case 'QueueReordered': {
      const byId = new Map(s.queuedPrompts.map((prompt) => [prompt.id, prompt]));
      const reordered = ev.ids.map((id) => byId.get(id)!).filter(Boolean);
      const { queuedPrompts, effects: queueEffects } =
        s.phase.kind === 'ready' && !s.agentTurnActive && s.backgroundAgentCount === 0
          ? dequeuePromptEffects(reordered)
          : { queuedPrompts: reordered, effects: [] as Effect[] };
      return {
        state: { ...s, queuedPrompts },
        effects: [{ type: 'state' }, ...queueEffects],
      };
    }

    case 'TurnEnded': {
      const active = activeTurnFromPhase(s.phase);
      if (!active) return warn(s, `TurnEnded with no active turn (phase: '${s.phase.kind}')`);
      const stopReason = ev.outcome.kind === 'stopped' ? ev.outcome.stopReason : null;
      const { queuedPrompts, effects: queueEffects } =
        s.backgroundAgentCount === 0
          ? dequeuePromptEffects(s.queuedPrompts)
          : { queuedPrompts: s.queuedPrompts, effects: [] as Effect[] };
      return {
        state: {
          ...s,
          phase: { kind: 'ready' },
          lastStopReason: stopReason,
          lastTurnErrored: ev.outcome.kind === 'errored',
          queuedPrompts,
          agentTurnActive: false,
        },
        effects: [
          { type: 'state' },
          { type: 'agentEvent', phase: ev.outcome.kind === 'errored' ? 'error' : 'stop' },
          { type: 'settleAgents', scope: 'turn', status: 'completed' },
          ...(ev.outcome.kind === 'errored' || stopReason === 'cancelled'
            ? ([{ type: 'settleAgents', scope: 'all', status: 'failed' }] as Effect[])
            : []),
          ...queueEffects,
        ],
      };
    }

    case 'AgentActivity': {
      const wasActive = s.agentTurnActive;
      const { queuedPrompts, effects: queueEffects } =
        !ev.active && s.phase.kind === 'ready' && s.backgroundAgentCount === 0
          ? dequeuePromptEffects(s.queuedPrompts)
          : { queuedPrompts: s.queuedPrompts, effects: [] as Effect[] };
      return {
        state: { ...s, agentTurnActive: ev.active, queuedPrompts },
        effects: [
          ...(wasActive !== ev.active ? ([{ type: 'state' }] as Effect[]) : []),
          ...queueEffects,
        ],
      };
    }

    case 'AgentsChanged': {
      const { queuedPrompts, effects: queueEffects } =
        ev.runningCount === 0 && s.phase.kind === 'ready'
          ? dequeuePromptEffects(s.queuedPrompts)
          : { queuedPrompts: s.queuedPrompts, effects: [] as Effect[] };
      return {
        state: { ...s, backgroundAgentCount: ev.runningCount, queuedPrompts },
        effects: [{ type: 'state' }, ...queueEffects],
      };
    }

    case 'CancellationRequested': {
      if (s.phase.kind !== 'working' && !s.agentTurnActive && s.backgroundAgentCount === 0) {
        return warn(s, `CancellationRequested in phase '${s.phase.kind}'`);
      }
      const drainEffects: Effect[] = s.pendingPermissions.map((p) => ({
        type: 'permissionResolved' as const,
        requestId: p.requestId,
        cancelled: true,
      }));
      if (s.phase.kind !== 'working') {
        return {
          state: { ...s, agentTurnActive: false, pendingPermissions: [] },
          effects: [
            ...drainEffects,
            { type: 'settleAgents', scope: 'all', status: 'failed' },
            { type: 'state' },
          ],
        };
      }
      return {
        state: { ...s, phase: { kind: 'cancelling', turn: s.phase.turn }, pendingPermissions: [] },
        effects: [...drainEffects, { type: 'state' }],
      };
    }

    case 'PermissionRequested':
      return {
        state: { ...s, pendingPermissions: [...s.pendingPermissions, ev.request] },
        effects: [{ type: 'permissionRequest', request: ev.request }],
      };

    case 'PermissionResolved':
      return {
        state: {
          ...s,
          pendingPermissions: s.pendingPermissions.filter((p) => p.requestId !== ev.requestId),
        },
        effects: [{ type: 'permissionResolved', requestId: ev.requestId, cancelled: false }],
      };

    case 'ProcessClosed': {
      const drainEffects: Effect[] = s.pendingPermissions.map((p) => ({
        type: 'permissionResolved' as const,
        requestId: p.requestId,
        cancelled: true,
      }));
      return {
        state: { ...s, phase: { kind: 'closed', exitCode: ev.exitCode }, pendingPermissions: [] },
        effects: [
          ...drainEffects,
          { type: 'settleAgents', scope: 'all', status: 'failed' },
          { type: 'state' },
          { type: 'closed', exitCode: ev.exitCode },
        ],
      };
    }
  }
}

function warn(
  s: SessionMachineState,
  message: string
): { state: SessionMachineState; effects: Effect[] } {
  return { state: s, effects: [{ type: 'warn', message }] };
}

function makeTurn(s: SessionMachineState): ControlTurn {
  return { id: makeTurnId(s.conversationId, s.nextTurnIndex) };
}

function dequeuePromptEffects(queuedPrompts: readonly QueuedPrompt[]): {
  queuedPrompts: readonly QueuedPrompt[];
  effects: Effect[];
} {
  const [next, ...rest] = queuedPrompts;
  return next
    ? { queuedPrompts: rest, effects: [{ type: 'sendPrompt', prompt: next }] }
    : { queuedPrompts, effects: [] };
}

export function isPromptReady(lifecycle: SessionLifecycle): boolean {
  return lifecycle === 'ready';
}

export function projectSessionState(s: SessionMachineState): SessionState {
  const activeTurn = activeTurnFromPhase(s.phase);
  const lifecycle = phaseToLifecycle(s.phase);
  const isWorking = s.phase.kind === 'working' || s.phase.kind === 'cancelling';
  const isGenerating = isWorking || s.agentTurnActive || s.backgroundAgentCount > 0;
  return {
    lifecycle,
    activeTurnId: activeTurn?.id ?? null,
    pendingPermissions: structuredClone([...s.pendingPermissions]),
    lastStopReason: s.lastStopReason,
    lastTurnErrored: s.lastTurnErrored,
    queuedPrompts: structuredClone([...s.queuedPrompts]),
    agentTurnActive: s.agentTurnActive,
    backgroundAgentCount: s.backgroundAgentCount,
    isGenerating,
    canSubmit: isPromptReady(lifecycle),
    canCancel: s.phase.kind === 'working' || s.agentTurnActive || s.backgroundAgentCount > 0,
  };
}

export class SessionMachine {
  private readonly machine: Machine<
    SessionMachineState,
    Command,
    DomainEvent,
    Effect,
    AcpRuntimeError,
    SessionMachineContext
  >;

  constructor(conversationId: string) {
    this.machine = createMachine(
      {
        decide,
        evolve,
      },
      initialMachineState(conversationId)
    );
  }

  get phase(): SessionPhase {
    return this.machine.current().phase;
  }
  get lifecycle(): SessionLifecycle {
    return phaseToLifecycle(this.machine.current().phase);
  }
  get pendingPermissions(): readonly AcpPermissionRequest[] {
    return this.machine.current().pendingPermissions;
  }
  get nextTurnIndex(): number {
    return this.machine.current().nextTurnIndex;
  }
  get lastStopReason(): StopReason | null {
    return this.machine.current().lastStopReason;
  }
  get queuedPrompts(): readonly QueuedPrompt[] {
    return this.machine.current().queuedPrompts;
  }
  get agentTurnActive(): boolean {
    return this.machine.current().agentTurnActive;
  }
  get backgroundAgentCount(): number {
    return this.machine.current().backgroundAgentCount;
  }
  get isWorking(): boolean {
    const phase = this.machine.current().phase;
    return phase.kind === 'working' || phase.kind === 'cancelling';
  }
  get canSubmit(): boolean {
    return isPromptReady(this.lifecycle);
  }
  get canCancel(): boolean {
    const state = this.machine.current();
    return (
      state.phase.kind === 'working' || state.agentTurnActive || state.backgroundAgentCount > 0
    );
  }
  get isGenerating(): boolean {
    const state = this.machine.current();
    return this.isWorking || state.agentTurnActive || state.backgroundAgentCount > 0;
  }

  dispatch(
    cmd: Command,
    ctx: SessionMachineContext = emptySessionMachineContext()
  ): Result<Effect[], AcpRuntimeError> {
    const result = this.machine.dispatch(cmd, ctx);
    return result.success ? ok([...result.data]) : result;
  }

  apply(...events: DomainEvent[]): Effect[] {
    return [...this.machine.apply(...events)];
  }

  sessionState(): SessionState {
    return projectSessionState(this.machine.current());
  }

  current(): SessionMachineState {
    return this.machine.current();
  }

  subscribe(
    listener: (batch: MachineBatch<SessionMachineState, Command, DomainEvent, Effect>) => void
  ): Unsubscribe {
    return this.machine.subscribe(listener);
  }
}
// The state machine for the ACP Session
