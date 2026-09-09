import { describe, expect, it } from 'vitest';
import { createRendererBootGate } from './renderer-boot-gate';

function deferred(): { promise: Promise<void>; resolve(): void } {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

describe('renderer boot gate', () => {
  it('stays pending after the backend completes until the renderer loads', async () => {
    const gate = createRendererBootGate();
    const waiting = gate.waitForBackend(Promise.resolve());
    let settled = false;
    void waiting.finally(() => {
      settled = true;
    });

    await Promise.resolve();
    expect(settled).toBe(false);

    gate.loaded();
    await expect(waiting).resolves.toBeUndefined();
  });

  it('rejects and aborts when the renderer fails after the backend resolves', async () => {
    const gate = createRendererBootGate();
    const error = new Error('renderer never loaded');
    const waiting = gate.waitForBackend(Promise.resolve());

    gate.fail(error);

    await expect(waiting).rejects.toBe(error);
    expect(gate.signal.aborted).toBe(true);
    expect(gate.signal.reason).toBe(error);
  });

  it('rejects and aborts while the backend remains in flight', async () => {
    const gate = createRendererBootGate();
    const backend = deferred();
    const error = new Error('renderer crashed');
    const waiting = gate.waitForBackend(backend.promise);

    gate.fail(error);

    await expect(waiting).rejects.toBe(error);
    expect(gate.signal.aborted).toBe(true);
    backend.resolve();
  });
});
