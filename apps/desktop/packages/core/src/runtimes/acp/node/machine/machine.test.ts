import { isErr, isOk } from '@emdash/shared';
import { describe, expect, it } from 'vitest';
import type { AcpPermissionRequest } from '#runtimes/acp/api';
import type { SessionMachineState } from './machine';
import {
  activeTurnFromPhase,
  decide,
  evolve,
  initialMachineState,
  phaseToLifecycle,
  SessionMachine,
} from './machine';

const CONV_ID = 'conv-test';
const prompt = { id: 'prompt-1', text: 'hello', createdAt: 100, updatedAt: 100 };

function makeReady(): SessionMachineState {
  return evolve(initialMachineState(CONV_ID), { type: 'SessionReady' }).state;
}

function makeWorking(): SessionMachineState {
  const ready = makeReady();
  const result = decide(ready, { type: 'Prompt', prompt });
  if (!isOk(result)) throw new Error('decide Prompt failed');
  return evolve(ready, result.data[0]).state;
}

const permRequest: AcpPermissionRequest = {
  requestId: 'req-1',
  toolCall: {
    kind: 'unknown-tool-call',
    id: 'permission:req-1',
    seq: 0,
    toolCallId: 'req-1',
    title: 'Permission request',
    status: 'running',
    toolKind: null,
    name: 'Permission request',
  },
  options: [{ optionId: 'allow', name: 'Allow', kind: 'allow_once' }],
};

describe('initialMachineState', () => {
  it('starts in "starting" phase', () => {
    const s = initialMachineState(CONV_ID);
    expect(phaseToLifecycle(s.phase)).toBe('starting');
    expect(s.pendingPermissions).toHaveLength(0);
  });
});

describe('decide Prompt', () => {
  it('accepted when ready', () => {
    const result = decide(makeReady(), { type: 'Prompt', prompt });
    expect(isOk(result)).toBe(true);
    if (!isOk(result)) return;
    expect(result.data).toEqual([{ type: 'PromptStarted', prompt }]);
  });

  it('queues while a turn is already in flight', () => {
    const result = decide(makeWorking(), { type: 'Prompt', prompt });
    expect(isOk(result)).toBe(true);
    if (!isOk(result)) return;
    expect(result.data).toEqual([{ type: 'PromptQueued', prompt }]);
  });

  it('queues while background agents are running', () => {
    const state = evolve(makeReady(), { type: 'AgentsChanged', runningCount: 1 }).state;
    const result = decide(state, { type: 'Prompt', prompt });
    expect(isOk(result)).toBe(true);
    if (!isOk(result)) return;
    expect(result.data).toEqual([{ type: 'PromptQueued', prompt }]);
  });
});

describe('decide QueuePrompt', () => {
  it('queues while a turn is already in flight', () => {
    const result = decide(makeWorking(), { type: 'QueuePrompt', prompt });
    expect(isOk(result)).toBe(true);
    if (!isOk(result)) return;
    expect(result.data).toEqual([{ type: 'PromptQueued', prompt }]);
  });

  it('queues while the session is starting', () => {
    const result = decide(initialMachineState(CONV_ID), { type: 'QueuePrompt', prompt });
    expect(isOk(result)).toBe(true);
    if (!isOk(result)) return;
    expect(result.data).toEqual([{ type: 'PromptQueued', prompt }]);
  });
});

describe('lifecycle control', () => {
  it('starting -> replaying -> ready', () => {
    const s0 = initialMachineState(CONV_ID);
    const { state: s1 } = evolve(s0, { type: 'ReplayStarted' });
    expect(phaseToLifecycle(s1.phase)).toBe('replaying');
    expect(activeTurnFromPhase(s1.phase)?.id).toBe('conv-test:turn:0');

    const { state: s2 } = evolve(s1, { type: 'ReplayEnded', status: 'complete' });
    expect(phaseToLifecycle(s2.phase)).toBe('ready');
    expect(activeTurnFromPhase(s2.phase)).toBeNull();
  });

  it('drains one queued prompt when a fresh session becomes ready', () => {
    const queued = { id: 'prompt-2', text: 'queued', createdAt: 200, updatedAt: 200 };
    const s0 = evolve(initialMachineState(CONV_ID), { type: 'PromptQueued', prompt: queued }).state;
    const { state, effects } = evolve(s0, { type: 'SessionReady' });

    expect(state.queuedPrompts).toHaveLength(0);
    expect(effects).toContainEqual({ type: 'sendPrompt', prompt: queued });
  });

  it('drains one queued prompt when replay completes', () => {
    const queued = { id: 'prompt-2', text: 'queued', createdAt: 200, updatedAt: 200 };
    const replaying = evolve(initialMachineState(CONV_ID), { type: 'ReplayStarted' }).state;
    const queuedState = evolve(replaying, { type: 'PromptQueued', prompt: queued }).state;
    const { state, effects } = evolve(queuedState, {
      type: 'ReplayEnded',
      status: 'complete',
    });

    expect(state.queuedPrompts).toHaveLength(0);
    expect(effects).toContainEqual({ type: 'sendPrompt', prompt: queued });
  });

  it('ready -> working -> ready and preserves stop reason', () => {
    const s0 = makeReady();
    const { state: s1, effects } = evolve(s0, { type: 'PromptStarted', prompt });
    expect(phaseToLifecycle(s1.phase)).toBe('working');
    expect(activeTurnFromPhase(s1.phase)?.id).toBe('conv-test:turn:0');
    expect(effects.some((e) => e.type === 'agentEvent' && e.phase === 'start')).toBe(true);

    const { state: s2 } = evolve(s1, {
      type: 'TurnEnded',
      outcome: { kind: 'stopped', stopReason: 'end_turn' },
    });
    expect(phaseToLifecycle(s2.phase)).toBe('ready');
    expect(s2.lastStopReason).toBe('end_turn');
    expect(s2.lastTurnErrored).toBe(false);
  });

  it('retains whether the last turn errored and clears it after a successful turn', () => {
    const errored = evolve(makeWorking(), {
      type: 'TurnEnded',
      outcome: { kind: 'errored' },
    }).state;
    const retained = evolve(errored, { type: 'AgentActivity', active: true }).state;

    expect(errored.lastTurnErrored).toBe(true);
    expect(retained.lastTurnErrored).toBe(true);

    const working = evolve(errored, { type: 'PromptStarted', prompt }).state;
    const completed = evolve(working, {
      type: 'TurnEnded',
      outcome: { kind: 'stopped', stopReason: 'end_turn' },
    }).state;

    expect(completed.lastTurnErrored).toBe(false);
  });

  it('drains one queued prompt when a turn ends', () => {
    const queued = { id: 'prompt-2', text: 'queued', createdAt: 200, updatedAt: 200 };
    const s0 = evolve(makeWorking(), { type: 'PromptQueued', prompt: queued }).state;
    const { state, effects } = evolve(s0, {
      type: 'TurnEnded',
      outcome: { kind: 'stopped', stopReason: 'end_turn' },
    });

    expect(state.queuedPrompts).toHaveLength(0);
    expect(effects).toContainEqual({ type: 'sendPrompt', prompt: queued });
  });

  it('keeps queued prompts waiting when a turn ends while background agents run', () => {
    const queued = { id: 'prompt-2', text: 'queued', createdAt: 200, updatedAt: 200 };
    let state = evolve(makeWorking(), { type: 'PromptQueued', prompt: queued }).state;
    state = evolve(state, { type: 'AgentsChanged', runningCount: 1 }).state;
    const result = evolve(state, {
      type: 'TurnEnded',
      outcome: { kind: 'stopped', stopReason: 'end_turn' },
    });

    expect(result.state.queuedPrompts).toEqual([queued]);
    expect(result.effects).not.toContainEqual({ type: 'sendPrompt', prompt: queued });
  });

  it('drains one queued prompt when background agents stop', () => {
    const queued = { id: 'prompt-2', text: 'queued', createdAt: 200, updatedAt: 200 };
    let state = evolve(makeReady(), { type: 'AgentsChanged', runningCount: 1 }).state;
    state = evolve(state, { type: 'PromptQueued', prompt: queued }).state;
    const result = evolve(state, { type: 'AgentsChanged', runningCount: 0 });

    expect(result.state.queuedPrompts).toHaveLength(0);
    expect(result.effects).toContainEqual({ type: 'sendPrompt', prompt: queued });
  });

  it('tracks agent activity and background agent counts', () => {
    const active = evolve(makeReady(), { type: 'AgentActivity', active: true }).state;
    expect(active.agentTurnActive).toBe(true);

    const counted = evolve(active, { type: 'AgentsChanged', runningCount: 2 }).state;
    expect(counted.backgroundAgentCount).toBe(2);
  });

  it('cancel drains pending permissions', () => {
    let s = makeWorking();
    s = evolve(s, { type: 'PermissionRequested', request: permRequest }).state;
    const { state, effects } = evolve(s, { type: 'CancellationRequested' });
    expect(phaseToLifecycle(state.phase)).toBe('cancelling');
    expect(state.pendingPermissions).toHaveLength(0);
    expect(effects).toContainEqual({
      type: 'permissionResolved',
      requestId: 'req-1',
      cancelled: true,
    });
  });

  it('cancel is valid while only background agents are running', () => {
    const state = evolve(makeReady(), { type: 'AgentsChanged', runningCount: 1 }).state;
    const decision = decide(state, { type: 'Cancel' });
    expect(isOk(decision)).toBe(true);
    if (!isOk(decision)) return;
    expect(decision.data).toEqual([{ type: 'CancellationRequested' }]);

    const result = evolve(state, { type: 'CancellationRequested' });
    expect(result.effects).toContainEqual({
      type: 'settleAgents',
      scope: 'all',
      status: 'failed',
    });
  });
});

describe('permissions and config validation', () => {
  it('guards ResolvePermission against unknown ids', () => {
    const result = decide(makeWorking(), {
      type: 'ResolvePermission',
      requestId: 'unknown',
      optionId: 'allow',
    });
    expect(isErr(result)).toBe(true);
  });

  it('accepts ResolvePermission for pending requests', () => {
    const s = evolve(makeWorking(), { type: 'PermissionRequested', request: permRequest }).state;
    const result = decide(s, { type: 'ResolvePermission', requestId: 'req-1', optionId: 'allow' });
    expect(isOk(result)).toBe(true);
  });

  it('validates modes and config options from caller-supplied context', () => {
    expect(
      isOk(decide(makeReady(), { type: 'SetMode', modeId: 'default' }, { modeIds: ['default'] }))
    ).toBe(true);
    expect(
      isOk(
        decide(
          makeReady(),
          { type: 'SetConfigOption', configId: 'reasoning_effort', value: 'high' },
          { configOptionIds: ['reasoning_effort'] }
        )
      )
    ).toBe(true);
    expect(isErr(decide(makeReady(), { type: 'SetMode', modeId: 'missing' }))).toBe(true);
  });

  it('edits and reorders queued prompts', () => {
    const queuedA = { id: 'a', text: 'a', createdAt: 100, updatedAt: 100 };
    const queuedB = { id: 'b', text: 'b', createdAt: 100, updatedAt: 100 };
    let state = evolve(makeWorking(), { type: 'PromptQueued', prompt: queuedA }).state;
    state = evolve(state, { type: 'PromptQueued', prompt: queuedB }).state;
    state = evolve(state, {
      type: 'QueuedPromptEdited',
      id: 'a',
      input: { text: 'edited' },
      updatedAt: 200,
    }).state;
    state = evolve(state, { type: 'QueueReordered', ids: ['b', 'a'] }).state;

    expect(state.queuedPrompts.map((entry) => entry.id)).toEqual(['b', 'a']);
    expect(state.queuedPrompts[1]).toMatchObject({ text: 'edited', updatedAt: 200 });
  });

  it('drains the selected prompt when reordering a legacy idle queue', () => {
    const queuedA = { id: 'a', text: 'a', createdAt: 100, updatedAt: 100 };
    const queuedB = { id: 'b', text: 'b', createdAt: 100, updatedAt: 100 };
    let state = evolve(makeReady(), { type: 'PromptQueued', prompt: queuedA }).state;
    state = evolve(state, { type: 'PromptQueued', prompt: queuedB }).state;

    const result = evolve(state, { type: 'QueueReordered', ids: ['b', 'a'] });

    expect(result.state.queuedPrompts.map((entry) => entry.id)).toEqual(['a']);
    expect(result.effects).toContainEqual({ type: 'sendPrompt', prompt: queuedB });
  });
});

describe('SessionMachine wrapper', () => {
  it('derives affordances from control state', () => {
    const machine = new SessionMachine(CONV_ID);
    machine.apply({ type: 'SessionReady' });
    expect(machine.canSubmit).toBe(true);
    expect(machine.canCancel).toBe(false);

    const result = machine.dispatch({ type: 'Prompt', prompt });
    expect(isOk(result)).toBe(true);
    expect(machine.canSubmit).toBe(false);
    expect(machine.canCancel).toBe(true);
    expect(machine.sessionState().activeTurnId).toBe('conv-test:turn:0');
  });
});
