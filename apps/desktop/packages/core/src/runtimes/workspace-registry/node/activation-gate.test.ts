import { describe, expect, it } from 'vitest';
import { WorkspaceActivationManager } from './activation';
import type { WorkspaceScriptRunner } from './scripts-plane';

// The artifact gate (dependency gating, spec: workspace-activation-speed): prepare and
// the setup→run chain wait for the background artifact clone to settle; workspaces
// without those scripts never wait.

function manager(options: {
  scripts: Record<string, string>;
  awaitArtifacts: (id: string) => Promise<void>;
  onRun: (script: string) => void;
}) {
  const runner: WorkspaceScriptRunner = {
    run: async (input) => {
      options.onRun(input.id);
      return { status: 'succeeded', outputTail: '' };
    },
  };
  return new WorkspaceActivationManager({
    publishActivation: () => undefined,
    setNotice: () => undefined,
    clearNotice: () => undefined,
    resetScriptSteps: () => undefined,
    recordScriptStep: () => undefined,
    recordActivated: async () => undefined,
    awaitArtifacts: options.awaitArtifacts,
    readScripts: async () => options.scripts,
    runner,
  });
}

describe('activation artifact gate', () => {
  it('honors personal auto-run toggles while leaving prepare enabled', async () => {
    const ran: string[] = [];
    const activation = new WorkspaceActivationManager({
      publishActivation: () => undefined,
      setNotice: () => undefined,
      clearNotice: () => undefined,
      resetScriptSteps: () => undefined,
      recordScriptStep: () => undefined,
      recordActivated: async () => undefined,
      resolveLifecycleConfig: async () => ({
        scripts: { prepare: 'prepare', setup: 'setup', run: 'run' },
        shellSetup: '',
        autoRunSetup: false,
        autoRunRun: false,
      }),
      runner: {
        run: async (input) => {
          ran.push(input.id);
          return { status: 'succeeded', outputTail: '' };
        },
      },
    });

    await activation.activate('ws', '/tmp/ws');
    expect(ran).toEqual(['prepare']);
    await activation.deactivate('ws');
  });

  it('prepare waits for the clone gate, then runs; setup follows the same gate', async () => {
    const events: string[] = [];
    let releaseGate!: () => void;
    const gate = new Promise<void>((resolve) => {
      releaseGate = resolve;
    });

    const activation = manager({
      scripts: { prepare: 'install', setup: 'seed' },
      awaitArtifacts: async () => {
        events.push('gate-awaited');
        await gate;
      },
      onRun: (script) => events.push(`run:${script}`),
    });

    const activate = activation.activate('ws', '/tmp/ws');
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(events).toEqual(['gate-awaited']);

    releaseGate();
    await activate;
    expect(events[0]).toBe('gate-awaited');
    expect(events).toContain('run:prepare');
    await activation.deactivate('ws');
  });

  it('a workspace without prepare/setup/run never awaits the gate', async () => {
    let gateAwaited = 0;
    const activation = manager({
      scripts: {},
      awaitArtifacts: async () => {
        gateAwaited += 1;
      },
      onRun: () => undefined,
    });

    await activation.activate('ws', '/tmp/ws');
    expect(gateAwaited).toBe(0);
    await activation.deactivate('ws');
  });

  it('a resolved gate (terminal clone failure opens it) lets scripts proceed', async () => {
    const ran: string[] = [];
    const activation = manager({
      scripts: { prepare: 'install' },
      // The runtime resolves the gate even for failed clones — dependents proceed.
      awaitArtifacts: async () => undefined,
      onRun: (script) => ran.push(script),
    });

    await activation.activate('ws', '/tmp/ws');
    expect(ran).toEqual(['prepare']);
    await activation.deactivate('ws');
  });
});
