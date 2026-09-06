import { ok } from '@emdash/shared';
import { noopLogger } from '@emdash/shared/logger';
import { createManualClock, type ManualClock } from '@emdash/shared/testing';
import { peek } from '@emdash/wire/state';
import { describe, expect, it, vi } from 'vitest';
import type { TuiAgentStartInput } from '#runtimes/tui-agents/api';
import type {
  AgentPluginHost,
  ITrustBehavior,
  ResolvedTuiProvider,
} from '#services/agent-plugins/api/plugins';
import type { ConversationLifecycleReporter } from '#services/conversation-reports/node';
import { createRecordingConversationLifecycleReporter } from '#services/conversation-reports/node/testing';
import type { IExecutionContext } from '#services/exec/api';
import { FakePtySpawner } from '#services/pty/testing';
import { createMemorySessionIntentStore } from '#services/session-intents/api';
import {
  expectNoSessionResidue,
  mapContainer,
  type LeakCheckContainer,
} from '#services/session-lifecycle/node/testing';
import { TuiAgentsRuntime } from './runtime';

function createRuntime(
  options: {
    clock?: ManualClock;
    lifecycle?: ConstructorParameters<typeof TuiAgentsRuntime>[0]['lifecycle'];
    exec?: Partial<IExecutionContext>;
    intents?: ReturnType<typeof createMemorySessionIntentStore>;
    conversationReports?: ConversationLifecycleReporter;
    hooks?: ResolvedTuiProvider['hooks'];
    trustWorkspace?: ITrustBehavior['trustWorkspace'];
  } = {}
) {
  const spawner = new FakePtySpawner();
  const hooks = options.hooks ?? { kind: 'none' as const };
  const provider: ResolvedTuiProvider = {
    name: 'Test Agent',
    prompt: { kind: 'argv' },
    hooks,
    buildCommand: () => ({ command: 'agent', args: ['run'], env: {} }),
  };
  const agentHost = {
    homeDir: '/home/test-user',
    resolveTuiProvider: vi.fn(() => provider),
    get: vi.fn(() => ({
      capabilities: { hooks },
      behavior: options.trustWorkspace ? { trust: { trustWorkspace: options.trustWorkspace } } : {},
    })),
    buildPromptCommand: vi.fn(() =>
      Promise.resolve(ok({ command: 'agent', args: ['run', 'hello world'], env: { AGENT: '1' } }))
    ),
  } as unknown as AgentPluginHost;
  const exec = {
    root: '',
    supportsLocalSpawn: true,
    exec: vi.fn(() => Promise.resolve({ stdout: '', stderr: '' })),
    execStreaming: vi.fn(() => Promise.resolve({ exitCode: 0 })),
    dispose: vi.fn(),
    ...options.exec,
  } satisfies IExecutionContext;
  const runtime = new TuiAgentsRuntime({
    agentHost,
    exec,
    intents: options.intents ?? createMemorySessionIntentStore(),
    conversationReports: options.conversationReports,
    spawner,
    clock: options.clock,
    lifecycle: options.lifecycle,
    logger: noopLogger,
  });
  return { runtime, spawner, agentHost, exec };
}

function startInput(overrides: Partial<TuiAgentStartInput> = {}): TuiAgentStartInput {
  return {
    conversationId: 'conversation-1',
    providerId: 'test',
    cwd: '/workspace',
    sessionId: null,
    model: null,
    initialPrompt: 'hello',
    cols: 120,
    rows: 30,
    ...overrides,
  };
}

describe('TuiAgentsRuntime', () => {
  it('starts eagerly and output attachment does not spawn', async () => {
    const { runtime, spawner } = createRuntime();

    await runtime.outputLog({ conversationId: 'conversation-1' }).snapshot();
    expect(spawner.specs).toHaveLength(0);

    await expect(runtime.startSession(startInput())).resolves.toEqual(ok({ outcome: 'started' }));

    expect(spawner.specs).toEqual([
      {
        command: 'agent',
        args: ['run', 'hello world'],
        cwd: '/workspace',
        env: {
          TERM: 'xterm-256color',
          COLORTERM: 'truecolor',
          TERM_PROGRAM: 'emdash',
          AGENT: '1',
        },
        cols: 120,
        rows: 30,
      },
    ]);

    await runtime.outputLog({ conversationId: 'conversation-1' }).snapshot();
    expect(spawner.specs).toHaveLength(1);
  });

  it('trusts the workspace only when the start input opts in', async () => {
    const trustWorkspace = vi.fn(async () => {});
    const { runtime } = createRuntime({ trustWorkspace });

    await runtime.startSession(startInput());
    expect(trustWorkspace).not.toHaveBeenCalled();

    await runtime.startSession(
      startInput({ conversationId: 'conversation-2', trustWorkspace: true })
    );
    expect(trustWorkspace).toHaveBeenCalledWith(expect.any(Object), {
      workspacePath: '/workspace',
    });
  });

  it('delivers hook events when hook installation fails', async () => {
    const { runtime, spawner } = createRuntime({
      hooks: { kind: 'config', scope: 'global', supportedEvents: ['stop'] },
    });
    vi.spyOn(runtime['hookInstaller'], 'ensureHooksInstalled').mockResolvedValue(false);

    await runtime.startSession(startInput());
    try {
      const env = spawner.specs[0]?.env;
      expect(env).toMatchObject({
        EMDASH_PTY_ID: 'conversation-1',
        EMDASH_HOOK_PORT: expect.stringMatching(/^\d+$/),
        EMDASH_HOOK_NONCE: expect.any(String),
        EMDASH_HOOK_TOKEN: expect.any(String),
      });
      if (!env?.EMDASH_HOOK_PORT || !env.EMDASH_HOOK_NONCE) {
        throw new Error('hook endpoint was not provided');
      }

      const response = await fetch(`http://127.0.0.1:${env.EMDASH_HOOK_PORT}/hook`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Emdash-Token': env.EMDASH_HOOK_NONCE,
          'X-Emdash-Pty-Id': 'conversation-1',
          'X-Emdash-Event-Type': 'stop',
        },
        body: '{}',
      });

      expect(response.status).toBe(200);
      expect(peek(runtime.agentStatesLiveModel.get(undefined)!.states.list)).toMatchObject({
        'conversation-1': { status: 'completed' },
      });
    } finally {
      await runtime.dispose();
    }
  });

  it('wraps command execution with shellSetup and tmux', async () => {
    const { runtime, spawner } = createRuntime();

    await runtime.startSession(
      startInput({
        shellSetup: 'source ~/.profile',
        tmuxSessionName: 'emdash-test',
      })
    );

    expect(spawner.specs[0]!.command).toBe('/bin/sh');
    expect(spawner.specs[0]!.args[0]).toBe('-c');
    expect(spawner.specs[0]!.args[1]).toContain('tmux -u attach-session');
    expect(spawner.specs[0]!.args[1]).toContain('emdash-test');
    expect(spawner.specs[0]!.args[1]).toContain("source ~/.profile && agent run 'hello world'");
  });

  it('attaches to an already running session without replacing config', async () => {
    const { runtime, spawner, agentHost } = createRuntime();

    await expect(runtime.startSession(startInput({ initialPrompt: 'first' }))).resolves.toEqual(
      ok({ outcome: 'started' })
    );
    await expect(
      runtime.resumeSession(
        startInput({ initialPrompt: 'second', sessionId: 'provider-session', cols: 90 })
      )
    ).resolves.toEqual(ok({ outcome: 'attached' }));

    expect(spawner.specs).toHaveLength(1);
    expect(agentHost.buildPromptCommand).toHaveBeenCalledTimes(1);
    expect(spawner.specs[0]!.cols).toBe(120);
  });

  it('returns a typed spawn failure when the PTY cannot be created', async () => {
    const { runtime, spawner } = createRuntime();
    spawner.failWith = new Error('spawn failed');

    const result = await runtime.startSession(startInput());

    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error).toMatchObject({
        type: 'spawn-failed',
        conversationId: 'conversation-1',
        message: 'Error: spawn failed',
      });
    }
    expect(peek(runtime.sessionsLiveModel.get(undefined)!.states.list)).toMatchObject({
      'conversation-1': { status: 'exited' },
    });
  });

  it('stops and deletes sessions while cleaning up tmux', async () => {
    const { runtime, spawner, exec } = createRuntime();

    await runtime.startSession(startInput({ tmuxSessionName: 'emdash-test' }));
    runtime.stopSession('conversation-1');

    expect(spawner.processes[0]!.killCount).toBeGreaterThan(0);
    await vi.waitFor(() => {
      expect(exec.exec).toHaveBeenCalledWith('tmux', ['kill-session', '-t', 'emdash-test']);
    });

    await runtime.startSession(startInput({ tmuxSessionName: 'emdash-test' }));
    await runtime.deleteSession('conversation-1');

    await vi.waitFor(() => {
      expect(exec.exec).toHaveBeenCalledTimes(2);
    });
  });

  it('falls back to a fresh session when resume exits immediately', async () => {
    const { runtime, spawner, agentHost } = createRuntime();

    const result = await runtime.resumeSession(startInput({ sessionId: 'provider-session' }));
    expect(result).toEqual(ok({ outcome: 'resumed' }));

    spawner.processes[0]!.emitExit({ exitCode: 0, signal: null });

    await vi.waitFor(() => {
      expect(spawner.specs).toHaveLength(2);
    });
    expect(agentHost.buildPromptCommand).toHaveBeenNthCalledWith(
      1,
      'test',
      expect.objectContaining({ isResuming: true, initialPrompt: undefined })
    );
    expect(agentHost.buildPromptCommand).toHaveBeenNthCalledWith(
      2,
      'test',
      expect.objectContaining({ isResuming: false, initialPrompt: 'hello' })
    );
  });

  it('deactivates idle sessions after the configured output inactivity period', async () => {
    const clock = createManualClock(0);
    const { runtime } = createRuntime({
      clock,
      lifecycle: { session: { kind: 'idle-after', outputMs: 1_000 }, sweepIntervalMs: 1_100 },
    });

    await runtime.startSession(startInput());

    await clock.advanceBy(1_200);

    await vi.waitFor(() => {
      expect(peek(runtime.sessionsLiveModel.get(undefined)!.states.list)).toEqual({});
    });
    expectNoSessionResidue('conversation-1', leakContainers(runtime));
  });

  it('idle sweep skips the tmux spawn when no sessions are tracked', async () => {
    const clock = createManualClock(0);
    const exec = vi.fn(() => Promise.resolve({ stdout: '', stderr: '' }));
    createRuntime({
      clock,
      lifecycle: { session: { kind: 'idle-after', outputMs: 1_000 }, sweepIntervalMs: 1_100 },
      exec: { exec },
    });

    await clock.advanceBy(1_200);

    expect(exec).not.toHaveBeenCalled();
  });

  it('uses batched tmux activity to keep detached tmux sessions active', async () => {
    const clock = createManualClock(1_000_000);
    const exec = vi.fn(() =>
      Promise.resolve({
        stdout: `emdash-test\t${Math.floor(clock.now() / 1000)}\n`,
        stderr: '',
      })
    );
    const { runtime, spawner } = createRuntime({
      clock,
      lifecycle: { session: { kind: 'idle-after', outputMs: 1_000 }, sweepIntervalMs: 1_100 },
      exec: { exec },
    });

    await runtime.startSession(startInput({ tmuxSessionName: 'emdash-test' }));

    await clock.advanceBy(1_200);

    expect(exec).toHaveBeenCalledWith('tmux', [
      'list-sessions',
      '-F',
      '#{session_name}\t#{session_activity}',
    ]);
    expect(spawner.processes[0]!.killCount).toBe(0);
    expect(peek(runtime.sessionsLiveModel.get(undefined)!.states.list)).toHaveProperty(
      'conversation-1'
    );
  });

  it('reconciles active intents only when their tmux session exists', async () => {
    const intents = createMemorySessionIntentStore();
    await intents.saveActive({
      conversationId: 'conversation-1',
      sessionId: 'provider-session',
      payload: startInput({
        sessionId: 'provider-session',
        tmuxSessionName: 'emdash-test',
      }),
    });
    const exec = vi.fn(() =>
      Promise.resolve({
        stdout: 'emdash-test\t42\n',
        stderr: '',
      })
    );
    const { runtime, spawner } = createRuntime({
      intents,
      exec: { exec },
    });

    await runtime.reconcile();

    expect(spawner.specs).toHaveLength(1);
    expect(peek(runtime.sessionsLiveModel.get(undefined)!.states.list)).toHaveProperty(
      'conversation-1'
    );
  });

  it('suspends active intents when their tmux session is missing', async () => {
    const intents = createMemorySessionIntentStore();
    await intents.saveActive({
      conversationId: 'conversation-1',
      payload: startInput({ tmuxSessionName: 'emdash-missing' }),
    });
    const { runtime } = createRuntime({ intents });

    await runtime.reconcile();

    expect(intents.snapshot()[0]).toMatchObject({
      conversationId: 'conversation-1',
      status: 'suspended',
      suspendedCause: 'process-lost',
    });
  });

  it('stopSession retains scrollback, stays sweep-inert, and remains resumable', async () => {
    const clock = createManualClock(0);
    const { runtime, spawner } = createRuntime({
      clock,
      lifecycle: { session: { kind: 'idle-after', outputMs: 1_000 }, sweepIntervalMs: 1_100 },
    });

    await runtime.startSession(startInput());
    spawner.processes[0]!.emitData('scrollback line\n');
    runtime.stopSession('conversation-1');

    const list = peek(runtime.sessionsLiveModel.get(undefined)!.states.list);
    expect(list['conversation-1']).toMatchObject({ status: 'exited' });
    const snapshot = await runtime.outputLog({ conversationId: 'conversation-1' }).snapshot();
    expect(JSON.stringify(snapshot)).toContain('scrollback line');

    // The stopped config tombstone keeps the key sweep-inert: nothing is evicted.
    await clock.advanceBy(2_400);
    expect(
      peek(runtime.sessionsLiveModel.get(undefined)!.states.list)['conversation-1']
    ).toBeDefined();

    await expect(runtime.startSession(startInput())).resolves.toEqual(ok({ outcome: 'started' }));
    expect(spawner.processes).toHaveLength(2);
  });

  it('deleteSession evicts a running session without leaking per-key state', async () => {
    const { runtime, spawner } = createRuntime();

    await runtime.startSession(startInput());
    spawner.processes[0]!.emitData('output\n');

    await runtime.deleteSession('conversation-1');

    expect(peek(runtime.sessionsLiveModel.get(undefined)!.states.list)).toEqual({});
    expectNoSessionResidue('conversation-1', leakContainers(runtime));
  });

  it('aborts reconcile without suspending intents when the tmux listing fails', async () => {
    const intents = createMemorySessionIntentStore();
    await intents.saveActive({
      conversationId: 'conversation-1',
      payload: startInput({ tmuxSessionName: 'emdash-test' }),
    });
    const exec = vi.fn(() => Promise.reject(new Error('tmux unavailable')));
    const { runtime, spawner } = createRuntime({ intents, exec: { exec } });

    await runtime.reconcile();

    expect(spawner.specs).toHaveLength(0);
    expect(intents.snapshot()[0]).toMatchObject({
      conversationId: 'conversation-1',
      status: 'active',
    });
  });

  it('removes persisted TUI intent when a session is killed', async () => {
    const intents = createMemorySessionIntentStore();
    const { runtime, spawner } = createRuntime({ intents });

    await runtime.startSession(startInput({ tmuxSessionName: 'emdash-test' }));
    await vi.waitFor(() => expect(intents.snapshot()).toHaveLength(1));

    await runtime.killSession('conversation-1');

    expect(spawner.processes[0]!.killCount).toBeGreaterThan(0);
    await vi.waitFor(() => expect(intents.snapshot()).toEqual([]));
    expectNoSessionResidue('conversation-1', leakContainers(runtime));
  });
});

// Property conv.sole-writer / spec §7.4: session facts (spawn, hook-captured provider id,
// activity, end, resume outcome) flow from the TUI runtime into the conversation index via
// lifecycle reports.
describe('TuiAgentsRuntime conversation lifecycle reports', () => {
  it('reports a fresh session start with no provider session id and no resume outcome', async () => {
    const reports = createRecordingConversationLifecycleReporter();
    const { runtime } = createRuntime({ conversationReports: reports });

    await runtime.startSession(startInput());

    expect(reports.started).toEqual([
      { conversationId: 'conversation-1', providerSessionId: null, resumeOutcome: null },
    ]);
  });

  it('reports the caller-declared emdash-chosen handle on a fresh spawn (spec §3.1)', async () => {
    const reports = createRecordingConversationLifecycleReporter();
    const { runtime } = createRuntime({ conversationReports: reports });

    await runtime.startSession(startInput({ chosenSessionId: 'conversation-1' }));

    expect(reports.started).toEqual([
      {
        conversationId: 'conversation-1',
        providerSessionId: 'conversation-1',
        resumeOutcome: null,
      },
    ]);
  });

  it("reports 'loaded' on resume and 'replaced-by-new' when the resume spawn exits early", async () => {
    const reports = createRecordingConversationLifecycleReporter();
    const { runtime, spawner } = createRuntime({ conversationReports: reports });

    await runtime.resumeSession(startInput({ sessionId: 'provider-session' }));
    expect(reports.started).toEqual([
      {
        conversationId: 'conversation-1',
        providerSessionId: 'provider-session',
        resumeOutcome: 'loaded',
      },
    ]);

    spawner.processes[0]!.emitExit({ exitCode: 0, signal: null });
    await vi.waitFor(() => {
      expect(reports.started).toHaveLength(2);
    });
    expect(reports.started[1]).toEqual({
      conversationId: 'conversation-1',
      providerSessionId: null,
      resumeOutcome: 'replaced-by-new',
    });
  });

  it('reports hook-captured provider session ids through the id-changed callback', async () => {
    const reports = createRecordingConversationLifecycleReporter();
    const { runtime } = createRuntime({ conversationReports: reports });
    await runtime.startSession(startInput());

    // The hook server -> pipeline chain needs a live HTTP round-trip, so drive the state
    // seam it lands on directly; the runtime's constructor callback is what is under test.
    runtime['agentStates'].setProviderSessionId('conversation-1', 'captured-session');

    expect(reports.providerIds).toEqual([
      { conversationId: 'conversation-1', providerSessionId: 'captured-session' },
    ]);
  });

  it('reports session end on stop and on process exit', async () => {
    const reports = createRecordingConversationLifecycleReporter();
    const { runtime, spawner } = createRuntime({ conversationReports: reports });

    await runtime.startSession(startInput());
    runtime.stopSession('conversation-1');
    expect(reports.ended).toEqual(['conversation-1']);

    await runtime.startSession(startInput());
    spawner.processes[1]!.emitExit({ exitCode: 0, signal: null });
    await vi.waitFor(() => {
      expect(reports.ended).toEqual(['conversation-1', 'conversation-1']);
    });
  });

  it('reports session end when a running session is deleted', async () => {
    const reports = createRecordingConversationLifecycleReporter();
    const { runtime } = createRuntime({ conversationReports: reports });

    await runtime.startSession(startInput());
    await runtime.deleteSession('conversation-1');

    expect(reports.ended).toEqual(['conversation-1']);
  });
});

type RuntimeInternals = {
  sessions: Map<string, unknown>;
  logs: Map<string, unknown>;
  configs: Map<string, unknown>;
  generations: Map<string, unknown>;
  unexpectedRespawns: Map<string, unknown>;
  registry: { get(key: string): unknown };
};

/** Reflects over the runtime's per-key maps so the shared leak check can see them. */
function leakContainers(runtime: TuiAgentsRuntime): LeakCheckContainer[] {
  const internals = runtime as unknown as RuntimeInternals;
  return [
    mapContainer('sessions', internals.sessions),
    mapContainer('logs', internals.logs),
    mapContainer('configs', internals.configs),
    mapContainer('generations', internals.generations),
    mapContainer('unexpectedRespawns', internals.unexpectedRespawns),
    { name: 'ptyRegistry', has: (key) => internals.registry.get(key) !== undefined },
    {
      name: 'sessionsList',
      has: (key) => key in peek(runtime.sessionsLiveModel.get(undefined)!.states.list),
    },
    {
      name: 'agentStatesList',
      has: (key) => key in peek(runtime.agentStatesLiveModel.get(undefined)!.states.list),
    },
  ];
}
