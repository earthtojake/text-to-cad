import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import z from 'zod';
import { linkedIssue } from '@core/primitives/linked-issues/api';
import { taskLifecycleStatuses } from './tasks';

const initialQueuePromptSchema = z.object({
  text: z.string(),
  hiddenContext: z.string().optional(),
});

const v1Schema = z.object({
  version: z.literal('1'),
  name: z.string(),
  linkedIssue: linkedIssue.asNested().optional(),
  initialConversation: z
    .object({
      id: z.string(),
      provider: z.string(),
      title: z.string().optional(),
      autoApprove: z.boolean().optional(),
      initialPrompt: z.string().optional(),
      initialQueue: z.array(initialQueuePromptSchema).optional(),
      model: z.string().optional(),
      type: z.enum(['pty', 'acp']).optional(),
    })
    .optional(),
  initialStatus: taskLifecycleStatuses.optional(),
});

export const taskConfig = defineVersionedSchema().initial('1', v1Schema).build();

export const taskConfigSchema = taskConfig.schema;
export type TaskConfig = typeof taskConfig.Type;
