import { z } from 'zod';
import { workbenchLayout } from '@core/primitives/layouts/api';
import { defineView } from '@core/primitives/views/api';
import { taskViewScope } from './scopes';
import { taskSubject } from './subject';

export const taskViewLocationSchema = z.object({
  tabId: z.string(),
});

export const taskViewDef = defineView({
  id: 'task',
  params: z.object({
    projectId: z.string().min(1),
    taskId: z.string().min(1),
  }),
  layout: workbenchLayout,
  historyKey: ({ taskId }) => taskId,
  subject: ({ taskId }) => taskSubject({ taskId }),
  scope: ({ projectId, taskId }) => taskViewScope({ projectId, taskId }),
  location: {
    schema: taskViewLocationSchema,
    key: ({ tabId }) => tabId,
  },
  telemetryEvent: 'task_viewed',
});
