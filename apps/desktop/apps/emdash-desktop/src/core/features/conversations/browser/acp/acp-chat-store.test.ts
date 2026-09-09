import { describe, expect, it, vi } from 'vitest';
import {
  bindSessionTerminalOutputs,
  type TerminalOutputSnapshot,
} from './acp-terminal-output-binding';

class FakeLiveList<T> {
  private listeners = new Set<() => void>();

  constructor(private value: T) {}

  current(): T {
    return this.value;
  }

  onChange(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  set(value: T): void {
    this.value = value;
    for (const listener of this.listeners) listener();
  }
}

class FakeLineLog {
  private listeners = new Set<() => void>();
  private linesArr: string[];
  private truncatedFlag = false;
  private versionCounter = 0;

  constructor(initial: string[]) {
    this.linesArr = initial;
  }

  lines(): readonly string[] {
    return this.linesArr;
  }

  truncated(): boolean {
    return this.truncatedFlag;
  }

  version(): number {
    return this.versionCounter;
  }

  onFlush(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  push(line: string, options: { truncated?: boolean } = {}): void {
    this.linesArr.push(line);
    if (options.truncated) this.truncatedFlag = true;
    this.versionCounter += 1;
    for (const listener of this.listeners) listener();
  }
}

async function flushPromises(): Promise<void> {
  await Promise.resolve();
}

describe('bindSessionTerminalOutputs', () => {
  it('mirrors line snapshots per flush and clears them on terminal removal', async () => {
    const terminals = new FakeLiveList([{ terminalId: 'term-1' }]);
    const log = new FakeLineLog(['initial output']);
    const terminalOutput = vi.fn(async () => log);
    const outputs = new Map<string, TerminalOutputSnapshot | null>();

    const dispose = bindSessionTerminalOutputs(
      { terminals, terminalOutput },
      (terminalId, snapshot) => outputs.set(terminalId, snapshot)
    );
    await flushPromises();

    expect(terminalOutput).toHaveBeenCalledWith('term-1');
    expect(outputs.get('term-1')).toMatchObject({
      lines: ['initial output'],
      truncated: false,
      version: 0,
    });
    // The lines array passes through by reference — no join, no copy.
    expect(outputs.get('term-1')?.lines).toBe(log.lines());

    log.push('live output');
    expect(outputs.get('term-1')).toMatchObject({
      lines: ['initial output', 'live output'],
      version: 1,
    });

    terminals.set([]);
    expect(outputs.get('term-1')).toBeNull();

    log.push('late output');
    expect(outputs.get('term-1')).toBeNull();

    dispose();
  });

  it('collapses client-side and agent-side truncation into one flag', async () => {
    const terminals = new FakeLiveList([{ terminalId: 'term-1', truncated: false }]);
    const log = new FakeLineLog(['tail']);
    const outputs = new Map<string, TerminalOutputSnapshot | null>();

    const dispose = bindSessionTerminalOutputs(
      { terminals, terminalOutput: async () => log },
      (terminalId, snapshot) => outputs.set(terminalId, snapshot)
    );
    await flushPromises();
    expect(outputs.get('term-1')?.truncated).toBe(false);

    // Client-side eviction flags truncation on the next flush.
    log.push('more', { truncated: true });
    expect(outputs.get('term-1')?.truncated).toBe(true);

    dispose();
  });

  it('picks up the agent-side truncated flag on a terminals republish', async () => {
    const terminals = new FakeLiveList([{ terminalId: 'term-1', truncated: false }]);
    const log = new FakeLineLog(['tail']);
    const outputs = new Map<string, TerminalOutputSnapshot | null>();

    const dispose = bindSessionTerminalOutputs(
      { terminals, terminalOutput: async () => log },
      (terminalId, snapshot) => outputs.set(terminalId, snapshot)
    );
    await flushPromises();
    expect(outputs.get('term-1')?.truncated).toBe(false);

    terminals.set([{ terminalId: 'term-1', truncated: true }]);
    expect(outputs.get('term-1')?.truncated).toBe(true);

    dispose();
  });

  it('clears mirrored outputs when disposed', async () => {
    const terminals = new FakeLiveList([{ terminalId: 'term-1' }]);
    const log = new FakeLineLog(['initial output']);
    const outputs = new Map<string, TerminalOutputSnapshot | null>();

    const dispose = bindSessionTerminalOutputs(
      { terminals, terminalOutput: async () => log },
      (terminalId, snapshot) => outputs.set(terminalId, snapshot)
    );
    await flushPromises();

    dispose();
    expect(outputs.get('term-1')).toBeNull();

    log.push('late output');
    expect(outputs.get('term-1')).toBeNull();
  });
});
