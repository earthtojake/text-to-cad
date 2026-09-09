import { projectViewDef } from '@core/features/projects/contributions/views';
import { settingsViewDef } from '@core/features/settings/contributions/views';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { homeViewDef } from '@core/features/workbench/contributions/views';
import { defineViewCatalog } from '@core/primitives/views/api';

export const viewCatalog = defineViewCatalog([
  homeViewDef,
  projectViewDef,
  taskViewDef,
  settingsViewDef,
] as const);

export type ViewId = (typeof viewCatalog.defs)[number]['id'];
