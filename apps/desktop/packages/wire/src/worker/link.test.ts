import { describe, expect, it } from 'vitest';
import { WireError } from '../api/protocol';
import { FakeWorkerProcess } from '../testing';
import { WorkerLink } from './link';
import { WORKER_READY_SIGNAL } from './protocol';

describe('WorkerLink', () => {
  it('filters control messages and fences stale generations', () => {
    const link = new WorkerLink();
    const first = new FakeWorkerProcess({ entry: 'first' });
    const second = new FakeWorkerProcess({ entry: 'second' });
    const messages: unknown[] = [];
    const ready: number[] = [];

    link.onMessage((message) => messages.push(message));
    link.onReady((generation) => ready.push(generation));
    link.attach(1, first);
    link.handleMessage(1, WORKER_READY_SIGNAL);
    link.handleMessage(1, {
      kind: 'wire-worker-frame',
      channel: 'runtime',
      payload: { kind: 'result', id: 'one', ok: true, value: 1 },
    });
    link.attach(2, second);
    link.handleMessage(1, {
      kind: 'wire-worker-frame',
      channel: 'runtime',
      payload: { kind: 'result', id: 'stale', ok: true, value: 0 },
    });
    link.handleMessage(2, { kind: 'result', id: 'ignored', ok: true, value: -1 });
    link.handleMessage(2, {
      kind: 'wire-worker-frame',
      channel: 'runtime',
      payload: { kind: 'result', id: 'two', ok: true, value: 2 },
    });

    expect(ready).toEqual([1]);
    expect(messages).toEqual([
      { kind: 'result', id: 'one', ok: true, value: 1 },
      { kind: 'result', id: 'two', ok: true, value: 2 },
    ]);
  });

  it('fails posts while no ready generation is attached', () => {
    const link = new WorkerLink();

    expect(() => link.post({ kind: 'cancel', id: 'call' })).toThrow(WireError);

    const process = new FakeWorkerProcess({ entry: 'worker' });
    link.attach(1, process);
    expect(() => link.post({ kind: 'cancel', id: 'call' })).toThrow(WireError);
    link.markReady(1);
    link.post({ kind: 'cancel', id: 'call' });
    expect(process.parentMessages).toEqual([
      {
        kind: 'wire-worker-frame',
        channel: 'runtime',
        payload: { kind: 'cancel', id: 'call' },
      },
    ]);
  });
});
