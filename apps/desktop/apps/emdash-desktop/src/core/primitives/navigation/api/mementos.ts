import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { z } from 'zod';
import { defineMemento } from '@core/primitives/mementos/api';
import { appSubject } from '@core/primitives/subjects/api';

// The memento ids keep their historical 'workbench.*' prefixes so persisted
// navigation state written before the move into this primitive keeps loading.

const workbenchNavigationV1Schema = z.object({
  version: z.literal('1'),
  currentViewId: z.string(),
  viewParams: z.record(z.string(), z.unknown()),
});

export const workbenchNavigationSchema = defineVersionedSchema()
  .initial('1', workbenchNavigationV1Schema)
  .build();

export type WorkbenchNavigationState = typeof workbenchNavigationSchema.Type;

export const workbenchNavigationMemento = defineMemento({
  id: 'workbench.navigation',
  subject: appSubject,
  schema: workbenchNavigationSchema,
  default: {
    version: '1' as const,
    currentViewId: 'home',
    viewParams: {},
  },
});

const workbenchHistoryEntrySchema = z.object({
  viewId: z.string(),
  params: z.unknown(),
  location: z.unknown().optional(),
});

const workbenchHistoryV1Schema = z.object({
  version: z.literal('1'),
  entries: z.array(workbenchHistoryEntrySchema),
  index: z.number().int(),
});

export const workbenchHistorySchema = defineVersionedSchema()
  .initial('1', workbenchHistoryV1Schema)
  .build();

export type WorkbenchHistoryState = typeof workbenchHistorySchema.Type;

export const workbenchHistoryMemento = defineMemento({
  id: 'workbench.history',
  subject: appSubject,
  schema: workbenchHistorySchema,
  default: {
    version: '1' as const,
    entries: [],
    index: -1,
  },
  retention: { tier: 'persisted' },
});
