import { afterEach, describe, expect, it, vi } from 'vitest';
import { startCadArtifactPolling } from './cad-artifact-poller';
import { CadTurnLedger } from './cad-turn-ledger';

const disposers: Array<() => void> = [];
afterEach(() => {
  disposers.splice(0).forEach((dispose) => dispose());
  vi.useRealTimers();
});

function setup(scan = vi.fn(async () => true)) {
  vi.useFakeTimers();
  const ledger = new CadTurnLedger();
  ledger.seed([['a', 'working']]);
  const mount = () => {
    const stop = startCadArtifactPolling({ ledger, conversationIds: () => ['a'], scan });
    disposers.push(stop);
    return stop;
  };
  return { ledger, scan, mount, end: () => ledger.apply([['a', 'idle']], [['a', 'working']]) };
}

describe('live CAD discovery', () => {
  it('scans during a running turn, performs a final scan, then stops', async () => {
    const { mount, scan, end } = setup();
    mount();
    await vi.advanceTimersByTimeAsync(750);
    expect(scan).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2_000);
    expect(scan).toHaveBeenCalledTimes(2);
    end();
    await vi.advanceTimersByTimeAsync(750);
    expect(scan).toHaveBeenCalledTimes(3);
    await vi.advanceTimersByTimeAsync(30_000);
    expect(scan).toHaveBeenCalledTimes(3);
  });

  it('retries unsettled files and failed scans before acknowledging completion', async () => {
    const scan = vi
      .fn(async () => true)
      .mockResolvedValueOnce(false)
      .mockRejectedValueOnce(new Error('temporary disconnect'));
    const { mount, ledger, end } = setup(scan);
    end();
    mount();
    await vi.advanceTimersByTimeAsync(750);
    expect(ledger.pendingTurns(['a'])).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(2_000);
    expect(ledger.pendingTurns(['a'])).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(4_000);
    expect(ledger.pendingTurns(['a'])).toHaveLength(0);
  });

  it('serializes slow scans and catches a turn ending while one is in flight', async () => {
    let complete!: (settled: boolean) => void;
    const scan = vi
      .fn(async () => true)
      .mockImplementationOnce(
        () =>
          new Promise<boolean>((resolve) => {
            complete = resolve;
          })
      );
    const { mount, ledger, end } = setup(scan);
    mount();
    await vi.advanceTimersByTimeAsync(750);
    end();
    await vi.advanceTimersByTimeAsync(10_000);
    expect(scan).toHaveBeenCalledTimes(1);
    complete(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(ledger.pendingTurns(['a'])).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(2_000);
    expect(scan).toHaveBeenCalledTimes(2);
    expect(ledger.pendingTurns(['a'])).toHaveLength(0);
  });

  it('leaves an interrupted scan pending for the next mount', async () => {
    let complete!: (settled: boolean) => void;
    const scan = vi
      .fn(async () => true)
      .mockImplementationOnce(
        () =>
          new Promise<boolean>((resolve) => {
            complete = resolve;
          })
      );
    const { mount, ledger, end } = setup(scan);
    end();
    const stop = mount();
    await vi.advanceTimersByTimeAsync(750);
    stop();
    complete(true);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(ledger.pendingTurns(['a'])).toHaveLength(1);
    expect(scan).toHaveBeenCalledTimes(1);
    mount();
    await vi.advanceTimersByTimeAsync(750);
    expect(ledger.pendingTurns(['a'])).toHaveLength(0);
  });
});
