import { describe, it, expect } from 'vitest';
import {
  FakeAcpProcessHost,
  FakeAcpTerminalProcess,
  createRecordingListener,
} from '#runtimes/acp/node/acp-test-support';
import { AgentTerminalManager } from './terminal-manager';

function makeManager() {
  const host = new FakeAcpProcessHost();
  const recording = createRecordingListener();
  const manager = new AgentTerminalManager(host, recording.listener);
  return { host, recording, manager };
}

async function createTerminal(
  manager: AgentTerminalManager,
  host: FakeAcpProcessHost,
  conversationId: string,
  command = 'echo',
  proc?: FakeAcpTerminalProcess
): Promise<string> {
  if (proc) host.nextTerminal = proc;
  return manager.create(conversationId, {
    command,
    args: [],
    env: {},
    cwd: '/tmp',
  });
}

describe('AgentTerminalManager.supportsTerminals()', () => {
  it('returns true when host.spawnTerminal is present', () => {
    const { manager } = makeManager();
    expect(manager.supportsTerminals()).toBe(true);
  });

  it('returns false when host.spawnTerminal is absent', () => {
    const host = new FakeAcpProcessHost();
    const recording = createRecordingListener();
    // Remove the optional method
    (host as { spawnTerminal?: unknown }).spawnTerminal = undefined;
    const manager = new AgentTerminalManager(host, recording.listener);
    expect(manager.supportsTerminals()).toBe(false);
  });
});

describe('AgentTerminalManager.create()', () => {
  it('spawns via host and emits onTerminalCreated', async () => {
    const { host, recording, manager } = makeManager();
    const terminalId = await createTerminal(manager, host, 'conv-1', 'ls');

    expect(terminalId).toBeTypeOf('string');
    expect(recording.terminalCreated).toHaveLength(1);
    expect(recording.terminalCreated[0]).toMatchObject({
      conversationId: 'conv-1',
      terminalId,
      command: 'ls',
      cwd: '/tmp',
    });
  });

  it('throws if host does not support terminals', async () => {
    const host = new FakeAcpProcessHost();
    const recording = createRecordingListener();
    (host as { spawnTerminal?: unknown }).spawnTerminal = undefined;
    const manager = new AgentTerminalManager(host, recording.listener);

    await expect(
      manager.create('conv-1', { command: 'ls', args: [], env: {}, cwd: '/tmp' })
    ).rejects.toThrow('does not support terminal spawning');
  });

  it('forwards stdout output as onTerminalOutput', async () => {
    const { host, recording, manager } = makeManager();
    const proc = new FakeAcpTerminalProcess();
    const terminalId = await createTerminal(manager, host, 'conv-1', 'cat', proc);

    proc.pushOutput('hello');
    expect(recording.terminalOutput).toHaveLength(1);
    expect(recording.terminalOutput[0]).toMatchObject({
      conversationId: 'conv-1',
      terminalId,
      chunk: 'hello',
      truncated: false,
    });
  });

  it('emits onTerminalExit when process exits', async () => {
    const { host, recording, manager } = makeManager();
    const proc = new FakeAcpTerminalProcess();
    const terminalId = await createTerminal(manager, host, 'conv-1', 'sleep', proc);

    proc.triggerExit({ exitCode: 0, signal: null });
    expect(recording.terminalExit).toHaveLength(1);
    expect(recording.terminalExit[0]).toMatchObject({
      conversationId: 'conv-1',
      terminalId,
      exitStatus: { exitCode: 0, signal: null },
    });
  });
});

describe('AgentTerminalManager.get()', () => {
  it('returns the terminal after creation', async () => {
    const { host, manager } = makeManager();
    const terminalId = await createTerminal(manager, host, 'conv-1');
    expect(manager.get(terminalId)).toBeDefined();
  });

  it('returns undefined for unknown id', () => {
    const { manager } = makeManager();
    expect(manager.get('unknown-id')).toBeUndefined();
  });
});

describe('AgentTerminalManager listing', () => {
  it("listByConversation returns only that conversation's terminals", async () => {
    const { host, manager } = makeManager();
    await createTerminal(manager, host, 'conv-1');
    await createTerminal(manager, host, 'conv-1');
    await createTerminal(manager, host, 'conv-2');

    expect(manager.listByConversation('conv-1')).toHaveLength(2);
    expect(manager.listByConversation('conv-2')).toHaveLength(1);
    expect(manager.listByConversation('conv-unknown')).toHaveLength(0);
  });

  it('listAll returns terminals across all conversations', async () => {
    const { host, manager } = makeManager();
    await createTerminal(manager, host, 'conv-1');
    await createTerminal(manager, host, 'conv-2');

    expect(manager.listAll()).toHaveLength(2);
  });

  it('snapshots contain the right metadata', async () => {
    const { host, manager } = makeManager();
    const terminalId = await createTerminal(manager, host, 'conv-1', 'grep');

    const [snap] = manager.listByConversation('conv-1');
    expect(snap.terminalId).toBe(terminalId);
    expect(snap.command).toBe('grep');
    expect(snap.exitStatus).toBeNull();
  });
});

describe('AgentTerminalManager.release()', () => {
  it('disposes the terminal and emits onTerminalReleased', async () => {
    const { host, recording, manager } = makeManager();
    const proc = new FakeAcpTerminalProcess();
    const terminalId = await createTerminal(manager, host, 'conv-1', 'echo', proc);

    manager.release(terminalId);

    expect(proc.killFn).toHaveBeenCalledWith('SIGTERM');
    expect(recording.terminalReleased).toHaveLength(1);
    expect(recording.terminalReleased[0]).toMatchObject({ conversationId: 'conv-1', terminalId });
    expect(manager.get(terminalId)).toBeUndefined();
    expect(manager.listByConversation('conv-1')).toHaveLength(0);
  });

  it('is a no-op for unknown id', () => {
    const { recording, manager } = makeManager();
    expect(() => manager.release('no-such-id')).not.toThrow();
    expect(recording.terminalReleased).toHaveLength(0);
  });
});

describe('AgentTerminalManager.disposeConversation()', () => {
  it('disposes all terminals for a conversation and emits onTerminalReleased for each', async () => {
    const { host, recording, manager } = makeManager();
    const proc1 = new FakeAcpTerminalProcess();
    const proc2 = new FakeAcpTerminalProcess();
    await createTerminal(manager, host, 'conv-1', 'a', proc1);
    await createTerminal(manager, host, 'conv-1', 'b', proc2);
    await createTerminal(manager, host, 'conv-2', 'c');

    manager.disposeConversation('conv-1');

    expect(proc1.killFn).toHaveBeenCalledWith('SIGTERM');
    expect(proc2.killFn).toHaveBeenCalledWith('SIGTERM');
    expect(recording.terminalReleased).toHaveLength(2);
    expect(recording.terminalReleased.every((e) => e.conversationId === 'conv-1')).toBe(true);
    expect(manager.listByConversation('conv-1')).toHaveLength(0);
    // conv-2 untouched
    expect(manager.listByConversation('conv-2')).toHaveLength(1);
    expect(manager.listAll()).toHaveLength(1);
  });

  it('is a no-op for unknown conversation', () => {
    const { recording, manager } = makeManager();
    expect(() => manager.disposeConversation('no-such-conv')).not.toThrow();
    expect(recording.terminalReleased).toHaveLength(0);
  });
});

describe('AgentTerminalManager.killAll()', () => {
  it('disposes every terminal and emits onTerminalReleased for each', async () => {
    const { host, recording, manager } = makeManager();
    const proc1 = new FakeAcpTerminalProcess();
    const proc2 = new FakeAcpTerminalProcess();
    await createTerminal(manager, host, 'conv-1', 'a', proc1);
    await createTerminal(manager, host, 'conv-2', 'b', proc2);

    manager.killAll();

    expect(proc1.killFn).toHaveBeenCalledWith('SIGTERM');
    expect(proc2.killFn).toHaveBeenCalledWith('SIGTERM');
    expect(recording.terminalReleased).toHaveLength(2);
    expect(manager.listAll()).toHaveLength(0);
  });

  it('leaves the manager empty after being called', async () => {
    const { host, manager } = makeManager();
    await createTerminal(manager, host, 'conv-1');
    manager.killAll();
    manager.killAll(); // idempotent — no throw
    expect(manager.listAll()).toHaveLength(0);
  });
});

describe('AgentTerminalManager narrated terminals', () => {
  const flush = () => new Promise<void>((resolve) => setImmediate(resolve));

  it('adopts, streams, and exits a terminal the agent runs itself', async () => {
    const { recording, manager } = makeManager();
    manager.adoptNarrated('conv-1', { terminalId: 'call-9', command: 'pytest -q', cwd: '/repo' });
    expect(recording.terminalCreated[0]).toMatchObject({
      conversationId: 'conv-1',
      terminalId: 'call-9',
      command: 'pytest -q',
      cwd: '/repo',
    });

    expect(manager.appendNarratedOutput('call-9', 'collected 3 items\n')).toBe(true);
    await flush();
    expect(recording.terminalOutput.map((e) => e.chunk).join('')).toBe('collected 3 items\n');

    // Providers re-send the whole output at exit; only the unseen tail is appended.
    expect(
      manager.exitNarrated('call-9', { exitCode: 0, signal: null }, 'collected 3 items\n3 passed\n')
    ).toBe(true);
    await flush();
    expect(recording.terminalOutput.map((e) => e.chunk).join('')).toBe(
      'collected 3 items\n3 passed\n'
    );
    expect(recording.terminalExit[0]).toMatchObject({
      terminalId: 'call-9',
      exitStatus: { exitCode: 0 },
    });
    expect(manager.get('call-9')?.outputSnapshot()).toMatchObject({
      output: 'collected 3 items\n3 passed\n',
      exitStatus: { exitCode: 0, signal: null },
    });
  });

  it('adopts an id once and ignores narration for terminals it does not own', () => {
    const { recording, manager } = makeManager();
    manager.adoptNarrated('conv-1', { terminalId: 'call-1', command: 'ls', cwd: '/repo' });
    manager.adoptNarrated('conv-1', { terminalId: 'call-1', command: 'ls again', cwd: '/repo' });
    expect(recording.terminalCreated).toHaveLength(1);
    expect(manager.appendNarratedOutput('unknown', 'x')).toBe(false);
    expect(manager.exitNarrated('unknown', { exitCode: 1, signal: null })).toBe(false);
  });

  it('releases narrated terminals like spawned ones', () => {
    const { recording, manager } = makeManager();
    manager.adoptNarrated('conv-1', { terminalId: 'call-2', command: 'ls', cwd: '/repo' });
    manager.release('call-2');
    expect(manager.get('call-2')).toBeUndefined();
    expect(recording.terminalReleased[0]).toMatchObject({ terminalId: 'call-2' });
    expect(manager.appendNarratedOutput('call-2', 'late')).toBe(false);
  });
});
