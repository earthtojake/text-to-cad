import { z } from 'zod';
import { workbenchLayout } from '@core/primitives/layouts/api';
import { defineView } from '@core/primitives/views/api';
import { projectSubject } from './subject';

export const projectViewDef = defineView({
  id: 'project',
  params: z.object({
    projectId: z.string().min(1),
  }),
  layout: workbenchLayout,
  subject: ({ projectId }) => projectSubject({ projectId }),
  telemetryEvent: 'project_viewed',
});
