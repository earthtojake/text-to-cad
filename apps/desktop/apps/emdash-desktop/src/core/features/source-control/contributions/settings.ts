import { z } from 'zod';
import type { ChangesViewMode } from '@core/primitives/app-settings/api';
import { defineSettingsContribution } from '@core/primitives/settings/api';

const changesViewModeSchema = z.object({
  unstaged: z.enum(['flat', 'tree']),
  staged: z.enum(['flat', 'tree']),
  pr: z.enum(['flat', 'tree']),
});

export const changesViewModeSettingsContribution = defineSettingsContribution<
  'changesViewMode',
  ChangesViewMode
>({
  key: 'changesViewMode',
  schema: changesViewModeSchema,
  defaults: {
    unstaged: 'flat',
    staged: 'flat',
    pr: 'flat',
  },
});
