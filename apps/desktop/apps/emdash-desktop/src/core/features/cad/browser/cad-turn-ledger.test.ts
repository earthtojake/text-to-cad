import { describe, expect, it } from 'vitest';
import { CadTurnLedger } from './cad-turn-ledger';

function clock(start = 1_000) {
  let now = start;
  return { now: () => now, tick: (ms: number) => (now += ms) };
}

describe('CadTurnLedger', () => {
  it('records when a turn starts and ends, keeping the original start', () => {
    const c = clock();
    const ledger = new CadTurnLedger(c.now);
    ledger.apply([['a', 'working']], [['a', 'idle']]);
    c.tick(5_000);
    ledger.apply([['a', 'idle']], [['a', 'working']]);
    expect(ledger.turns.get('a')).toEqual({ startedAt: 1_000, endedAt: 6_000, revealed: false });
  });

  it('keeps each task’s pending turns until acknowledged', () => {
    const c = clock();
    const ledger = new CadTurnLedger(c.now);
    ledger.apply(
      [
        ['a', 'working'],
        ['b', 'idle'],
      ],
      [
        ['a', 'idle'],
        ['b', 'idle'],
      ]
    );
    c.tick(1_000);
    ledger.apply(
      [
        ['a', 'working'],
        ['b', 'working'],
      ],
      [
        ['a', 'working'],
        ['b', 'idle'],
      ]
    );
    c.tick(1_000);
    ledger.apply(
      [
        ['a', 'idle'],
        ['b', 'idle'],
      ],
      [
        ['a', 'working'],
        ['b', 'working'],
      ]
    );
    expect(ledger.pendingTurns(['a', 'b']).map(([, turn]) => turn.startedAt)).toEqual([
      1_000, 2_000,
    ]);
    expect(ledger.pendingTurns(['b'])).toHaveLength(1);
    expect(ledger.pendingTurns(['zzz'])).toEqual([]);
    ledger.markRevealed(ledger.pendingTurns(['a', 'b']));
    expect(ledger.pendingTurns(['a', 'b'])).toEqual([]);
  });

  it('keeps a turn pending while it is still running', () => {
    const ledger = new CadTurnLedger(clock().now);
    ledger.apply([['a', 'working']], [['a', 'idle']]);
    expect(ledger.pendingTurns(['a'])).toHaveLength(1);
    ledger.markRevealed(ledger.pendingTurns(['a']));
    expect(ledger.turns.get('a')?.revealed).toBe(false);
  });

  it('keeps discovery active across permission waits without resetting the turn start', () => {
    const c = clock();
    const ledger = new CadTurnLedger(c.now);
    ledger.seed([['a', 'working']]);
    c.tick(5_000);
    ledger.apply([['a', 'awaiting-input']], [['a', 'working']]);
    ledger.markRevealed(ledger.pendingTurns(['a']));
    expect(ledger.turns.get('a')).toEqual({ startedAt: 1_000, endedAt: null, revealed: false });
    c.tick(5_000);
    ledger.apply([['a', 'working']], [['a', 'awaiting-input']]);
    expect(ledger.turns.get('a')?.startedAt).toBe(1_000);
    ledger.apply([['a', 'completed']], [['a', 'working']]);
    ledger.markRevealed(ledger.pendingTurns(['a']));
    expect(ledger.pendingTurns(['a'])).toEqual([]);
  });

  it('seeds conversations that are already working when a watcher attaches', () => {
    const c = clock(500);
    const ledger = new CadTurnLedger(c.now);
    ledger.seed([
      ['a', 'working'],
      ['b', 'idle'],
    ]);
    expect(ledger.turns.get('a')).toEqual({ startedAt: 500, endedAt: null, revealed: false });
    expect(ledger.turns.has('b')).toBe(false);
    ledger.seed([['a', 'working']]);
    expect(ledger.turns.get('a')?.startedAt).toBe(500);
  });

  it('does not acknowledge a turn that ended or restarted during an in-flight scan', () => {
    const ledger = new CadTurnLedger(clock().now);
    ledger.seed([['a', 'working']]);
    const activeScan = ledger.pendingTurns(['a']);
    ledger.apply([['a', 'idle']], [['a', 'working']]);
    ledger.markRevealed(activeScan);
    expect(ledger.pendingTurns(['a'])).toHaveLength(1);
    const endedScan = ledger.pendingTurns(['a']);
    ledger.apply([['a', 'working']], [['a', 'idle']]);
    ledger.apply([['a', 'idle']], [['a', 'working']]);
    ledger.markRevealed(endedScan);
    expect(ledger.pendingTurns(['a'])).toHaveLength(1);
  });
});
