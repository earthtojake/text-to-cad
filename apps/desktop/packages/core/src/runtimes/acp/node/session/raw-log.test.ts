import { describe, expect, it } from 'vitest';
import { RawAcpLog, type RawAcpEvent, type RawAcpLogMeta } from './raw-log';

function meta(): RawAcpLogMeta {
  return {
    conversationId: 'conversation-1',
    providerId: 'test',
    acpSessionId: 'session-1',
    createdAt: '2026-01-01T00:00:00.000Z',
  };
}

function promptEvent(content: string): RawAcpEvent {
  return { kind: 'prompt', sessionId: 'session-1', content };
}

describe('RawAcpLog', () => {
  it('evicts oldest entries once retained bytes exceed the byte cap', () => {
    const log = new RawAcpLog(meta(), { maxBytes: 600 });
    for (let i = 0; i < 20; i += 1) {
      log.record(promptEvent(`${i}`.padStart(3, '0').repeat(40)));
    }

    const { events } = log.snapshot();
    expect(events.length).toBeGreaterThan(0);
    expect(events.length).toBeLessThan(20);
    // The newest entry always survives; eviction removes from the front.
    expect(events.at(-1)?.seq).toBe(19);
    expect(events[0]?.seq).toBeGreaterThan(0);
    const seqs = events.map((entry) => entry.seq);
    expect(seqs).toEqual([...seqs].sort((a, b) => a - b));
  });

  it('keeps the newest entry even when it alone exceeds the byte cap', () => {
    const log = new RawAcpLog(meta(), { maxBytes: 100 });
    log.record(promptEvent('small'));
    log.record(promptEvent('x'.repeat(1_000)));

    const { events } = log.snapshot();
    expect(events).toHaveLength(1);
    expect(events[0]?.seq).toBe(1);
  });

  it('counts UTF-8 bytes, not UTF-16 code units', () => {
    // '€' is 1 UTF-16 code unit but 3 UTF-8 bytes; a code-unit counter would
    // undercount these entries ~3x and evict far too late.
    const entryBytes = Buffer.byteLength(JSON.stringify(promptEvent('€'.repeat(100))), 'utf8');
    const log = new RawAcpLog(meta(), { maxBytes: entryBytes * 3 });
    for (let i = 0; i < 6; i += 1) log.record(promptEvent('€'.repeat(100)));

    const { events } = log.snapshot();
    expect(events).toHaveLength(3);
    expect(events.map((entry) => entry.seq)).toEqual([3, 4, 5]);
  });

  it('still enforces the entry-count cap', () => {
    const log = new RawAcpLog(meta(), { maxEntries: 3 });
    for (let i = 0; i < 5; i += 1) log.record(promptEvent(`event-${i}`));

    const { events } = log.snapshot();
    expect(events.map((entry) => entry.seq)).toEqual([2, 3, 4]);
  });
});
