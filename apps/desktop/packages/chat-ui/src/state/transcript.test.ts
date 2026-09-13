import { describe, expect, it } from 'vitest';
import type { ChatMessage, TranscriptTurn } from '@/model';
import { applyTurnEvent } from '@/stories/_harness/turn-reducer';
import { createTranscript } from './transcript';

function msg(id: string, seq = 0, text = 'hi'): ChatMessage {
  return { kind: 'message', id, seq, role: 'user', text };
}

function turn(id: string, seq: number, ...items: ChatMessage[]): TranscriptTurn {
  return {
    id,
    seq,
    initiator: items.some((item) => item.role === 'user') ? 'user' : 'agent',
    items: items as TranscriptTurn['items'],
  };
}

function drive(
  tx: ReturnType<typeof createTranscript>,
  ...events: Parameters<typeof applyTurnEvent>[1][]
) {
  for (const event of events) {
    tx.activeTurn.set(applyTurnEvent(tx.activeTurn.get(), event), 'generating');
  }
}

describe('findItemById', () => {
  it('returns undefined for an empty transcript', () => {
    const tx = createTranscript();
    expect(tx.findItemById('x')).toBeUndefined();
  });

  it('finds seeded committed items', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, msg('a', 0), msg('b', 1), msg('c', 2))]);
    expect(tx.findItemById('a')?.id).toBe('a');
    expect(tx.findItemById('b')?.id).toBe('b');
    expect(tx.findItemById('c')?.id).toBe('c');
  });

  it('finds items in the active turn', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, msg('a', 0), msg('b', 1))]);
    drive(tx, { type: 'message_chunk', id: 'c', role: 'assistant', text: 'hi' });
    expect(tx.findItemById('c')?.id).toBe('c');
  });

  it('reset clears lookup state', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, msg('a', 0), msg('b', 1))]);
    tx.reset();
    expect(tx.findItemById('a')).toBeUndefined();
  });
});

describe('history', () => {
  it('seed replaces committed turns and clears active turn', () => {
    const tx = createTranscript();
    drive(tx, { type: 'message_chunk', id: 'x', role: 'assistant', text: 'live' });
    tx.history.seed([turn('t1', 0, msg('a', 0)), turn('t2', 1, msg('b', 0))]);
    expect(tx.state.committedTurns.map((t) => t.id)).toEqual(['t1', 't2']);
    expect(tx.state.activeTurnSnapshot).toBeNull();
  });

  it('prepends older turns before existing committed turns', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t2', 2, msg('c', 0))]);
    tx.history.prepend([turn('t0', 0, msg('a', 0)), turn('t1', 1, msg('b', 0))]);
    expect(tx.state.committedTurns.map((t) => t.id)).toEqual(['t0', 't1', 't2']);
  });

  it('append adds turns after committed history', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t0', 0, msg('a', 0))]);
    tx.history.append([turn('t1', 1, msg('b', 0)), turn('t2', 2, msg('c', 0))]);
    expect(tx.state.committedTurns.map((t) => t.id)).toEqual(['t0', 't1', 't2']);
  });
});

describe('activeTurn', () => {
  it('sets active turn snapshot and status', () => {
    const tx = createTranscript();
    tx.activeTurn.set(turn('active', 0, msg('x', 0)), 'generating');
    expect(tx.state.activeTurnSnapshot?.items).toHaveLength(1);
    expect(tx.state.activeTurnSnapshot?.items[0].id).toBe('x');
    expect(tx.state.turnStatus).toBe('generating');
  });

  it('reconcile patches in-place text growth for same item id', () => {
    const tx = createTranscript();
    tx.activeTurn.set(
      turn('active', 0, { kind: 'message', id: 'm1', seq: 0, role: 'assistant', text: 'Hello' }),
      'generating'
    );
    const ref1 = tx.state.activeTurnSnapshot!.items[0];
    tx.activeTurn.set(
      turn('active', 0, {
        kind: 'message',
        id: 'm1',
        seq: 0,
        role: 'assistant',
        text: 'Hello world',
      }),
      'generating'
    );
    expect(tx.state.activeTurnSnapshot!.items[0].id).toBe('m1');
    expect((tx.state.activeTurnSnapshot!.items[0] as ChatMessage).text).toBe('Hello world');
    expect((ref1 as ChatMessage).text).toBe('Hello world');
  });

  it('commit moves the active turn into committed turns and clears active state', () => {
    const tx = createTranscript();
    drive(tx, { type: 'message_chunk', id: 'a1', role: 'assistant', text: 'hi' });
    tx.activeTurn.commit('done');
    expect(tx.state.activeTurnSnapshot).toBeNull();
    expect(tx.state.turnStatus).toBe('done');
    expect(tx.findItemById('a1')).toBeDefined();
    expect(tx.state.committedTurns[0].outcome?.kind).toBe('done');
  });

  it('commit cancelled records cancelled outcome', () => {
    const tx = createTranscript();
    drive(tx, { type: 'message_chunk', id: 'a1', role: 'assistant', text: 'partial' });
    tx.activeTurn.commit('cancelled');
    expect(tx.state.turnStatus).toBe('cancelled');
    expect(tx.state.committedTurns[0].outcome?.kind).toBe('cancelled');
  });
});

describe('reset', () => {
  it('clears committed turns, active turn, and status', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, msg('a', 0))]);
    drive(tx, { type: 'message_chunk', id: 'c', role: 'assistant', text: 'hi' });
    tx.reset();
    expect(tx.state.committedTurns).toHaveLength(0);
    expect(tx.state.activeTurnSnapshot).toBeNull();
    expect(tx.state.turnStatus).toBe('done');
    expect(tx.findItemById('a')).toBeUndefined();
  });
});
