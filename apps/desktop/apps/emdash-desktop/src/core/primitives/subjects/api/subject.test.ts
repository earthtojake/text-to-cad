import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { appSubject, defineSubject, subjectSchema, type Subject } from './subject';

const taskSubject = defineSubject({
  kind: 'task',
  key: z.object({ taskId: z.string().uuid() }),
  encode: ({ taskId }) => taskId,
  retention: { maxAge: 1_000, maxEntries: 10 },
});

describe('defineSubject', () => {
  it('validates and encodes a domain identity', () => {
    const taskId = 'f326e4c9-7106-46b4-87d4-3c2cd5813765';

    expect(taskSubject({ taskId })).toEqual({ kind: 'task', key: taskId });
    expect(taskSubject.encode({ taskId })).toBe(taskId);
    expect(taskSubject.retention).toEqual({ maxAge: 1_000, maxEntries: 10 });
  });

  it('rejects invalid domain identities', () => {
    expect(() => taskSubject({ taskId: 'not-a-uuid' })).toThrow();
  });

  it('retains the subject kind in its output type', () => {
    const subject = taskSubject({ taskId: 'f326e4c9-7106-46b4-87d4-3c2cd5813765' });

    expectTypeOf(subject).toEqualTypeOf<Subject<'task'>>();
    expect(taskSubject.is(subject)).toBe(true);
    expect(taskSubject.is(appSubject({}))).toBe(false);
  });

  it('round-trips subjects through the wire schema', () => {
    const subject = taskSubject({ taskId: 'f326e4c9-7106-46b4-87d4-3c2cd5813765' });

    expect(subjectSchema.parse(subject)).toEqual(subject);
  });

  it('uses one stable application subject', () => {
    expect(appSubject({})).toEqual({ kind: 'app', key: '' });
  });
});
