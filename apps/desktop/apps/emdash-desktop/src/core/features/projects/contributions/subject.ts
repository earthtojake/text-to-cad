import { z } from 'zod';
import { defineSubject } from '@core/primitives/subjects/api';

export const projectSubject = defineSubject({
  kind: 'project',
  key: z.object({ projectId: z.string().min(1) }),
  encode: ({ projectId }) => projectId,
});
