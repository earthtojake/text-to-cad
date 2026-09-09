import { EDITOR_FILE_TREE_COMMAND_DEFS } from '@core/features/editor/contributions/commands';
import { SETTINGS_COMMAND_DEFS } from '@core/features/settings/contributions/commands';
import {
  TASK_COMMAND_DEFS,
  TASK_LIST_COMMAND_DEFS,
} from '@core/features/tasks/contributions/commands';
import { WORKBENCH_COMMAND_DEFS } from '@core/features/workbench/contributions/commands';
import { defineCommandCatalog } from '@core/primitives/commands/api';

export const COMMAND_CATALOG = defineCommandCatalog([
  ...SETTINGS_COMMAND_DEFS,
  ...EDITOR_FILE_TREE_COMMAND_DEFS,
  ...WORKBENCH_COMMAND_DEFS,
  ...TASK_COMMAND_DEFS,
  ...TASK_LIST_COMMAND_DEFS,
] as const);

export type CommandId = (typeof COMMAND_CATALOG.defs)[number]['id'];
