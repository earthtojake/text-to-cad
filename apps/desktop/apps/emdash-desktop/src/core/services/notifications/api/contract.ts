import { ok } from '@emdash/shared';
import { defineContract, eventStream, liveModel, liveState, mutation } from '@emdash/wire/rpc';
import { z } from 'zod';
import { reduceDismiss, reduceMarkAllRead, reduceMarkRead } from './optimistic';
import {
  notificationDeliveryEventSchema,
  notificationListSchema,
  notificationTargetSchema,
  type NotificationList,
} from './schemas';

const notificationMutationErrorSchema = z.object({
  message: z.string(),
});

const idsInputSchema = z.object({
  ids: z.array(z.string()),
});

const markReadInputSchema = idsInputSchema.extend({
  at: z.number().int(),
});

const markAllReadInputSchema = z.object({
  at: z.number().int(),
});

export const notificationsDomain = 'notifications' as const;

export const notificationsContract = defineContract({
  feed: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: notificationListSchema }),
    },
    mutations: {
      markRead: mutation(
        { input: markReadInputSchema, data: z.void(), error: notificationMutationErrorSchema },
        (ctx, input) => {
          ctx.produce('list', (draft) => reduceMarkRead(draft as NotificationList, input));
          return ok<void>();
        }
      ),
      markAllRead: mutation(
        { input: markAllReadInputSchema, data: z.void(), error: notificationMutationErrorSchema },
        (ctx, input) => {
          ctx.produce('list', (draft) => reduceMarkAllRead(draft as NotificationList, input));
          return ok<void>();
        }
      ),
      dismiss: mutation(
        { input: idsInputSchema, data: z.void(), error: notificationMutationErrorSchema },
        (ctx, input) => {
          ctx.produce('list', (draft) => reduceDismiss(draft as NotificationList, input));
          return ok<void>();
        }
      ),
    },
  }),
  delivery: eventStream({
    key: z.void().optional(),
    event: notificationDeliveryEventSchema,
  }),
});

export type NotificationsContract = typeof notificationsContract;
export type NotificationMutationError = z.infer<typeof notificationMutationErrorSchema>;
export { notificationTargetSchema };
