import { describe, expect, it } from 'vitest';
import { RipgrepJsonFramer, type RipgrepJsonFramerEvent } from './ripgrep-json-framer';

describe('RipgrepJsonFramer', () => {
  it('frames records for every possible UTF-8 byte chunking', () => {
    const input = Buffer.from('α\n😀\nz', 'utf8');
    const boundaryCount = input.length - 1;

    for (let boundaryMask = 0; boundaryMask < 2 ** boundaryCount; boundaryMask += 1) {
      const framer = createFramer();
      const events: RipgrepJsonFramerEvent[] = [];
      let start = 0;
      for (let boundary = 1; boundary < input.length; boundary += 1) {
        if ((boundaryMask & (1 << (boundary - 1))) === 0) continue;
        events.push(...framer.push(input.subarray(start, boundary)));
        start = boundary;
      }
      events.push(...framer.push(input.subarray(start)));
      events.push(...framer.finish());

      expect(events, `boundary mask ${boundaryMask.toString(2)}`).toEqual([
        { type: 'line', line: 'α' },
        { type: 'line', line: '😀' },
        { type: 'line', line: 'z' },
      ]);
    }
  });

  it('emits complete records immediately and flushes a final unterminated record', () => {
    const framer = createFramer();

    expect(framer.push(bytes('{"first":1}\n{"second":'))).toEqual([
      { type: 'line', line: '{"first":1}' },
    ]);
    expect(framer.push(bytes('2}'))).toEqual([]);
    expect(framer.finish()).toEqual([{ type: 'line', line: '{"second":2}' }]);
    expect(framer.finish()).toEqual([]);
  });

  it('does not invent a final empty record after a trailing newline', () => {
    const framer = createFramer();

    expect([...framer.push(bytes('{}\n')), ...framer.finish()]).toEqual([
      { type: 'line', line: '{}' },
    ]);
  });

  it('measures the record limit in UTF-8 bytes', () => {
    const exact = createFramer(4);
    expect(exact.push(bytes('😀\n'))).toEqual([{ type: 'line', line: '😀' }]);

    const oversized = createFramer(4);
    expect(oversized.push(bytes('😀a\n'))).toEqual([
      {
        type: 'oversized-record',
        maxRecordBytes: 4,
        observedRecordBytes: 5,
      },
    ]);
  });

  it('signals an oversized record once and recovers after its newline', () => {
    const framer = createFramer(5);

    expect(framer.push(bytes('123'))).toEqual([]);
    expect(framer.push(bytes('456'))).toEqual([
      {
        type: 'oversized-record',
        maxRecordBytes: 5,
        observedRecordBytes: 6,
      },
    ]);
    expect(framer.push(bytes('789\nok\n'))).toEqual([{ type: 'line', line: 'ok' }]);
    expect(framer.finish()).toEqual([]);
  });

  it('recovers from an oversized record followed by valid records in one chunk', () => {
    const framer = createFramer(5);

    expect(framer.push(bytes('123456789\nok\nend'))).toEqual([
      {
        type: 'oversized-record',
        maxRecordBytes: 5,
        observedRecordBytes: 9,
      },
      { type: 'line', line: 'ok' },
    ]);
    expect(framer.finish()).toEqual([{ type: 'line', line: 'end' }]);
  });

  it('signals each oversized record independently', () => {
    const framer = createFramer(2);

    expect(framer.push(bytes('abc\ndef\nok\n'))).toEqual([
      {
        type: 'oversized-record',
        maxRecordBytes: 2,
        observedRecordBytes: 3,
      },
      {
        type: 'oversized-record',
        maxRecordBytes: 2,
        observedRecordBytes: 3,
      },
      { type: 'line', line: 'ok' },
    ]);
  });

  it('does not emit an oversized unterminated record during finish', () => {
    const framer = createFramer(3);

    expect(framer.push(bytes('abcd'))).toEqual([
      {
        type: 'oversized-record',
        maxRecordBytes: 3,
        observedRecordBytes: 4,
      },
    ]);
    expect(framer.push(bytes('efgh'))).toEqual([]);
    expect(framer.finish()).toEqual([]);
  });

  it('rejects invalid limits and writes after finish', () => {
    expect(() => new RipgrepJsonFramer({ maxRecordBytes: 0 })).toThrow(RangeError);
    expect(() => new RipgrepJsonFramer({ maxRecordBytes: 1.5 })).toThrow(RangeError);

    const framer = createFramer();
    framer.finish();
    expect(() => framer.push(bytes('{}\n'))).toThrow(/after the framer has finished/);
  });
});

function createFramer(maxRecordBytes = 1024): RipgrepJsonFramer {
  return new RipgrepJsonFramer({ maxRecordBytes });
}

function bytes(value: string): Buffer {
  return Buffer.from(value, 'utf8');
}
