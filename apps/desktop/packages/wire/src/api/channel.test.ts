import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import { liveCursorEntrySchema, liveCursorSchema, liveUpdateSchema } from './channel';

describe('live protocol schemas', () => {
  it('parses live cursors and cursor entries', () => {
    expect(liveCursorSchema.parse({ generation: 1, sequence: 2 })).toEqual({
      generation: 1,
      sequence: 2,
    });
    expect(
      liveCursorEntrySchema.parse({
        model: 'files.tree',
        key: { rootPath: '/repo', sessionId: 'a' },
        cursor: { generation: 1, sequence: 2 },
      })
    ).toMatchObject({
      model: 'files.tree',
      cursor: { generation: 1, sequence: 2 },
    });
  });

  it('allows mutation IDs on live updates', () => {
    const update = liveUpdateSchema.parse({
      generation: 1,
      baseSequence: 0,
      sequence: 1,
      timestamp: 123,
      delta: [],
      mutationIds: ['m1'],
    });
    expect(update.mutationIds).toEqual(['m1']);
  });

  it('keeps transport-opaque delta values', () => {
    const delta = { chunk: 'hello' };
    const schema = liveUpdateSchema.extend({ delta: z.unknown() });
    expect(
      schema.parse({
        generation: 1,
        baseSequence: 0,
        sequence: 1,
        timestamp: 123,
        delta,
      }).delta
    ).toBe(delta);
  });
});
