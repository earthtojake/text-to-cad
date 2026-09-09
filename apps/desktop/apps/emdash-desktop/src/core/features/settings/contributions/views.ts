import { z } from 'zod';
import { workbenchLayout } from '@core/primitives/layouts/api';
import { defineView } from '@core/primitives/views/api';

export const settingsPageTabSchema = z.enum([
  'general',
  'interface',
  'browser',
  'repository',
  'prompts',
  'system',
  'workspaces-local',
  'conversations',
  'clis-models',
  'mcp',
  'skills',
  'connections',
  'docs',
]);

export type SettingsPageTab = z.infer<typeof settingsPageTabSchema>;

/**
 * Nested detail path: one segment per level (e.g. `[connectionId, projectId]`).
 * Legacy single-string values from persisted state or old history entries are
 * coerced to a one-element path.
 */
export const settingsDetailPathSchema = z.union([
  z.array(z.string()),
  z.string().transform((value) => [value]),
]);

export const settingsViewDef = defineView({
  id: 'settings',
  params: z.object({
    tab: settingsPageTabSchema.optional(),
    detail: settingsDetailPathSchema.optional(),
  }),
  layout: workbenchLayout,
  telemetryEvent: 'settings_viewed',
});
