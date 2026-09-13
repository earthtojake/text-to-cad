import { z } from 'zod';
import { workbenchLayout } from '@core/primitives/layouts/api';
import { defineView } from '@core/primitives/views/api';

export const homeViewDef = defineView({
  id: 'home',
  params: z.object({ projectId: z.string().optional(), draftId: z.string().optional() }),
  layout: workbenchLayout,
  historyKey: ({ draftId }) => draftId ?? '',
  telemetryEvent: 'home_viewed',
});

export function newChatDraftView(projectId?: string) {
  return homeViewDef({ projectId, draftId: crypto.randomUUID() });
}
