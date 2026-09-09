import { describe, expect, it } from 'vitest';
import { TerminalLiveRegistry } from './terminal-live-registry';

function makeRegistry() {
  const republishes: string[] = [];
  const registry = new TerminalLiveRegistry((conversationId) => republishes.push(conversationId));
  return { registry, republishes };
}

function createTerminal(registry: TerminalLiveRegistry, terminalId = 'term-1') {
  registry.hooks.onTerminalCreated({
    conversationId: 'conv-1',
    terminalId,
    command: 'echo',
    args: [],
    cwd: '/tmp',
  });
}

describe('TerminalLiveRegistry', () => {
  it('appends output chunks to the terminal log stream', () => {
    const { registry } = makeRegistry();
    createTerminal(registry);

    registry.hooks.onTerminalOutput({
      conversationId: 'conv-1',
      terminalId: 'term-1',
      chunk: 'hello ',
      truncated: false,
    });
    registry.hooks.onTerminalOutput({
      conversationId: 'conv-1',
      terminalId: 'term-1',
      chunk: 'world',
      truncated: false,
    });

    expect(registry.getTerminalLog('term-1')?.snapshot().data.text).toBe('hello world');
  });

  it('republishes conversation state only on create, exit, release, and truncation transition', () => {
    const { registry, republishes } = makeRegistry();
    createTerminal(registry);
    expect(republishes).toHaveLength(1);

    for (let i = 0; i < 100; i += 1) {
      registry.hooks.onTerminalOutput({
        conversationId: 'conv-1',
        terminalId: 'term-1',
        chunk: `chunk-${i}`,
        truncated: false,
      });
    }
    expect(republishes).toHaveLength(1);

    // First truncated chunk republishes once; further truncated chunks do not.
    registry.hooks.onTerminalOutput({
      conversationId: 'conv-1',
      terminalId: 'term-1',
      chunk: 'x',
      truncated: true,
    });
    registry.hooks.onTerminalOutput({
      conversationId: 'conv-1',
      terminalId: 'term-1',
      chunk: 'y',
      truncated: true,
    });
    expect(republishes).toHaveLength(2);

    registry.hooks.onTerminalExit({
      conversationId: 'conv-1',
      terminalId: 'term-1',
      exitStatus: { exitCode: 0, signal: null },
    });
    expect(republishes).toHaveLength(3);

    registry.hooks.onTerminalReleased({ conversationId: 'conv-1', terminalId: 'term-1' });
    expect(republishes).toHaveLength(4);
  });

  it('keeps memory-relevant state constant-size while chunks stream', () => {
    const { registry } = makeRegistry();
    createTerminal(registry);

    // Stream well past the 1 MB log cap; retained state must stay bounded.
    const chunk = 'x'.repeat(1024);
    for (let i = 0; i < 2048; i += 1) {
      registry.hooks.onTerminalOutput({
        conversationId: 'conv-1',
        terminalId: 'term-1',
        chunk,
        truncated: false,
      });
    }

    const snapshot = registry.getTerminalLog('term-1')?.snapshot();
    if (!snapshot) throw new Error('expected log snapshot');
    expect(snapshot.data.text.length).toBeLessThanOrEqual(1024 * 1024);
    expect(snapshot.data.truncated).toBe(true);
  });

  it('drops the log when the terminal is released', () => {
    const { registry } = makeRegistry();
    createTerminal(registry);
    expect(registry.getTerminalLog('term-1')).not.toBeNull();

    registry.hooks.onTerminalReleased({ conversationId: 'conv-1', terminalId: 'term-1' });
    expect(registry.getTerminalLog('term-1')).toBeNull();
  });
});
