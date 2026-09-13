import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { defineSubject } from '@core/primitives/subjects/api';
import {
  days,
  defineMemento,
  DEFAULT_PERSISTED_MAX_ENTRIES,
  DEFAULT_TRANSIENT_MAX_ENTRIES,
  type MementoValue,
} from './define-memento';

const taskSubject = defineSubject({
  kind: 'task',
  key: z.object({ taskId: z.string() }),
  encode: ({ taskId }) => taskId,
});

const drawerSchema = defineVersionedSchema()
  .initial(
    '1',
    z.object({
      version: z.literal('1'),
      open: z.boolean(),
    })
  )
  .build();

describe('defineMemento', () => {
  it('normalizes persisted retention defaults', () => {
    const definition = defineMemento({
      id: 'tasks.drawer',
      subject: taskSubject,
      schema: drawerSchema,
      default: { version: '1' as const, open: false },
    });

    expect(definition.retention).toEqual({
      tier: 'persisted',
      maxAge: days(60),
      maxEntries: DEFAULT_PERSISTED_MAX_ENTRIES,
    });
    expectTypeOf<MementoValue<typeof definition>>().toEqualTypeOf<{
      version: '1';
      open: boolean;
    }>();
  });

  it('normalizes transient retention defaults', () => {
    const definition = defineMemento({
      id: 'tasks.drawer-scroll',
      subject: taskSubject,
      schema: drawerSchema,
      default: { version: '1' as const, open: false },
      retention: { tier: 'transient' },
    });

    expect(definition.retention).toEqual({
      tier: 'transient',
      maxEntries: DEFAULT_TRANSIENT_MAX_ENTRIES,
    });
  });

  it('inherits retention defaults from the subject kind', () => {
    const boundedSubject = defineSubject({
      kind: 'bounded',
      key: z.string(),
      encode: (key) => key,
      retention: { maxAge: 123, maxEntries: 4 },
    });
    const definition = defineMemento({
      id: 'bounded.drawer',
      subject: boundedSubject,
      schema: drawerSchema,
      default: { version: '1' as const, open: false },
    });

    expect(definition.retention).toEqual({
      tier: 'persisted',
      maxAge: 123,
      maxEntries: 4,
    });
  });

  it('rejects empty ids', () => {
    expect(() =>
      defineMemento({
        id: ' ',
        subject: taskSubject,
        schema: drawerSchema,
        default: { version: '1' as const, open: false },
      })
    ).toThrow('must not be empty');
  });
});
