import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import { z } from 'zod';

export const notificationSoundSchema = z.enum(['needs_attention', 'task_complete']);

export type NotificationSound = z.infer<typeof notificationSoundSchema>;

export const notificationTargetSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('task'),
    projectId: z.string(),
    taskId: z.string(),
    conversationId: z.string().optional(),
  }),
  z.object({
    kind: z.literal('update'),
    version: z.string().optional(),
  }),
  z.object({ kind: z.literal('none') }),
]);

export type NotificationTarget = z.infer<typeof notificationTargetSchema>;

export const notificationSourceSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('conversation'),
    projectId: z.string(),
    taskId: z.string(),
    conversationId: z.string(),
  }),
  z.object({ kind: z.literal('app') }),
]);

export type NotificationSource = z.infer<typeof notificationSourceSchema>;

const notificationPayloadV1Schema = z.object({
  version: z.literal('1'),
  target: notificationTargetSchema,
  source: notificationSourceSchema,
  sound: notificationSoundSchema.nullable(),
});

export const notificationPayload = defineVersionedSchema()
  .initial('1', notificationPayloadV1Schema)
  .build();

export const notificationPayloadSchema = notificationPayload.schema;

export type NotificationPayload = typeof notificationPayload.Type;

export const notificationSchema = z.object({
  id: z.string(),
  kind: z.string(),
  groupKey: z.string(),
  title: z.string(),
  body: z.string(),
  target: notificationTargetSchema,
  source: notificationSourceSchema,
  sound: notificationSoundSchema.nullable(),
  count: z.number().int().nonnegative(),
  createdAt: z.number().int(),
  readAt: z.number().int().nullable(),
});

export type AppNotification = z.infer<typeof notificationSchema>;

export const notificationListSchema = z.record(z.string(), notificationSchema);

export type NotificationList = z.infer<typeof notificationListSchema>;

export const publishNotificationSchema = notificationSchema
  .omit({ id: true, count: true, createdAt: true, readAt: true })
  .extend({ dedupeKey: z.string().optional() });

export type PublishNotification = z.infer<typeof publishNotificationSchema>;

export const notificationDeliveryEventSchema = z.discriminatedUnion('type', [
  z.object({
    type: z.literal('sound'),
    sound: notificationSoundSchema,
    notificationId: z.string(),
  }),
  z.object({
    type: z.literal('open'),
    notificationId: z.string(),
    target: notificationTargetSchema,
  }),
]);

export type NotificationDeliveryEvent = z.infer<typeof notificationDeliveryEventSchema>;
