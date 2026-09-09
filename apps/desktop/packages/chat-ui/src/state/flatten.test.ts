import { unit } from '@core/units';
import type { ItemSegmenter, SegmentCtx, SegmentItem, UnitDef } from '@core/units';
import { describe, expect, it } from 'vitest';
import type { ChatItem, ChatMessage, TranscriptTurn } from '@/model';
import { applyTurnEvent } from '@/stories/_harness/turn-reducer';
import { collectUserTurnUnits, flattenTier, makeUnitsView } from './flatten';
import { createTranscript } from './transcript';

const MSG_MARGIN_TOP = 8;

function passthrough(kind: ChatItem['kind']): ItemSegmenter {
  return {
    kind,
    segment: (item: SegmentItem) => [unit(item.kind, item, item, { key: 'self' })],
  };
}

const STUB_SEGMENTERS: Record<string, ItemSegmenter> = {
  message: passthrough('message'),
  tool: passthrough('tool'),
  thinking: passthrough('thinking'),
  'file-op': passthrough('file-op'),
  execute: passthrough('execute'),
  diff: passthrough('diff'),
  'resource-link': passthrough('resource-link'),
  plan: passthrough('plan'),
};

function userMsg(id: string, seq = 0, text = 'hello'): ChatMessage {
  return { kind: 'message', id, seq, role: 'user', text };
}

function tool(id: string, seq = 0): ChatItem {
  return { kind: 'tool', id, seq, name: 'bash', status: 'done' } as ChatItem;
}

function turn(id: string, seq: number, ...items: ChatItem[]): TranscriptTurn {
  return {
    id,
    seq,
    initiator: items.some((item) => item.kind === 'message' && item.role === 'user')
      ? 'user'
      : 'agent',
    items: items as TranscriptTurn['items'],
  };
}

const segCtx = {
  caches: {},
  expanded: () => false,
  active: false,
  plan: () => null,
  pendingToolCallIds: () => new Set<string>(),
  terminalOutput: () => null,
} as unknown as SegmentCtx;

type StubUnitDefs = Record<string, Pick<UnitDef<unknown, Record<string, number>>, 'margin'>>;

const STUB_UNIT_DEFS: StubUnitDefs = {
  message: { margin: { top: 8, bottom: 8 } },
  tool: { margin: { top: 2, bottom: 2 } },
  thinking: { margin: { top: 6, bottom: 6 } },
  'file-op': { margin: { top: 2, bottom: 2 } },
  execute: { margin: { top: 2, bottom: 2 } },
  diff: { margin: { top: 2, bottom: 6 } },
  'resource-link': { margin: { top: 2, bottom: 2 } },
  plan: { margin: { top: 8, bottom: 8 } },
};

function driveEvent(
  tx: ReturnType<typeof createTranscript>,
  event: Parameters<typeof applyTurnEvent>[1]
) {
  tx.activeTurn.set(applyTurnEvent(tx.activeTurn.get(), event), 'generating');
}

function flattenCommitted(tx: ReturnType<typeof createTranscript>, unitDefs?: StubUnitDefs) {
  return flattenTier(tx.state.committedTurns, segCtx, STUB_SEGMENTERS, unitDefs);
}

function flattenActive(
  tx: ReturnType<typeof createTranscript>,
  prevKind?: string,
  unitDefs?: StubUnitDefs
) {
  const at = tx.state.activeTurnSnapshot;
  return flattenTier(
    at ? [at] : [],
    { ...segCtx, active: true },
    STUB_SEGMENTERS,
    unitDefs,
    prevKind
  );
}

function flattenAll(tx: ReturnType<typeof createTranscript>, unitDefs?: StubUnitDefs) {
  const c = flattenCommitted(tx, unitDefs);
  const prevKind = c.length > 0 ? c[c.length - 1].kind : undefined;
  const a = flattenActive(tx, prevKind, unitDefs);
  return makeUnitsView(c, a);
}

describe('flatten — basic', () => {
  it('returns empty view for an empty transcript', () => {
    const tx = createTranscript();
    expect(flattenAll(tx).length).toBe(0);
  });

  it('produces one unit per committed item', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, userMsg('a', 0), userMsg('b', 1), tool('c', 2))]);
    const view = flattenAll(tx);
    expect(view.length).toBe(3);
    expect(view.at(0)?.itemId).toBe('a');
    expect(view.at(1)?.itemId).toBe('b');
    expect(view.at(2)?.itemId).toBe('c');
  });

  it('unit ids are ${itemId}#self', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, userMsg('x'))]);
    expect(flattenAll(tx).at(0)?.id).toBe('x#self');
  });

  it('unit.data is the same committed item reference', () => {
    const tx = createTranscript();
    const item = userMsg('a');
    tx.history.seed([turn('t1', 0, item)]);
    const view = flattenAll(tx);
    expect(view.at(0)?.data).toBe(tx.state.committedTurns[0].items[0]);
  });
});

describe('flatten — gaps', () => {
  it('first unit has gapBefore = 0', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, userMsg('a', 0), tool('b', 1))]);
    expect(flattenAll(tx, STUB_UNIT_DEFS).at(0)?.gapBefore).toBe(0);
  });

  it('user to tool seam collapses to message margin', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, userMsg('a', 0), tool('b', 1))]);
    expect(flattenAll(tx, STUB_UNIT_DEFS).at(1)?.gapBefore).toBe(MSG_MARGIN_TOP);
  });

  it('tool to tool seam collapses adjacent margins', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, userMsg('u', 0), tool('a', 1), tool('b', 2))]);
    expect(flattenAll(tx, STUB_UNIT_DEFS).at(2)?.gapBefore).toBe(2);
  });
});

describe('flatten — active turn', () => {
  it('includes active turn items at the end', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, userMsg('a'))]);
    driveEvent(tx, { type: 'message_chunk', id: 'streaming', role: 'assistant', text: 'hi' });
    const view = flattenAll(tx);
    expect(view.length).toBe(2);
    expect(view.at(1)?.itemId).toBe('streaming');
  });

  it('first active unit gets gapBefore from committed last kind', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, userMsg('u1'))]);
    driveEvent(tx, { type: 'message_chunk', id: 'streaming', role: 'assistant', text: 'hi' });
    const committedUnits = flattenCommitted(tx, STUB_UNIT_DEFS);
    const activeUnits = flattenActive(
      tx,
      committedUnits[committedUnits.length - 1]?.kind,
      STUB_UNIT_DEFS
    );
    expect(activeUnits[0]?.gapBefore).toBe(8);
  });
});

describe('flatten — identity stability', () => {
  it('same committed turns produce stable unit ids and data refs', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, userMsg('a', 0), tool('b', 1))]);
    const r1 = flattenCommitted(tx);
    const r2 = flattenCommitted(tx);
    expect(r1[0].id).toBe(r2[0].id);
    expect(r1[1].id).toBe(r2[1].id);
    expect(r1[0].data).toBe(r2[0].data);
    expect(r1[0].data).toBe(tx.state.committedTurns[0].items[0]);
  });

  it('commit produces a committed turn distinct from the active proxy', () => {
    const tx = createTranscript();
    driveEvent(tx, { type: 'message_chunk', id: 'msg-1', role: 'assistant', text: 'hi' });
    const streaming = tx.state.activeTurnSnapshot?.items[0];
    tx.activeTurn.commit('done');
    const committed = tx.state.committedTurns[0].items[0];
    expect(committed).not.toBe(streaming);
    expect(flattenCommitted(tx)[0].data).toBe(committed);
  });
});

describe('collectUserTurnUnits', () => {
  it('returns empty array when no user messages', () => {
    const tx = createTranscript();
    tx.history.seed([turn('t1', 0, tool('a'))]);
    expect(collectUserTurnUnits(tx.state.committedTurns, flattenAll(tx))).toEqual([]);
  });

  it('returns correct unit indices for committed user messages only', () => {
    const tx = createTranscript();
    tx.history.seed([
      turn('t1', 0, userMsg('u1', 0), tool('t1', 1), userMsg('u2', 2), tool('t2', 3)),
    ]);
    driveEvent(tx, { type: 'message_chunk', id: 'streaming', role: 'user', text: 'hi' });
    const view = flattenAll(tx);
    const indices = collectUserTurnUnits(tx.state.committedTurns, view);
    expect(indices).toEqual([0, 2]);
  });
});
