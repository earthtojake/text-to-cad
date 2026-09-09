import { z } from 'zod';
import { defineViewScope } from '@core/primitives/view-scopes/api';
import { closeSettingsCommand } from './commands';

export const settingsScope = defineViewScope({
  id: 'settings',
  params: z.object({}),
  commands: [closeSettingsCommand] as const,
  activation: 'logical',
});
