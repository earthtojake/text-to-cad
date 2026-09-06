import { TASK_COMMAND_PALETTE_ITEMS } from '@core/features/tasks/contributions/palette';
import { WORKBENCH_COMMAND_PALETTE_ITEMS } from '@core/features/workbench/contributions/palette';
import { defineCommandPaletteCatalog } from '@core/primitives/palette/api';
import { COMMAND_CATALOG } from './command-catalog';

export const COMMAND_PALETTE_CATALOG = defineCommandPaletteCatalog(COMMAND_CATALOG, [
  ...WORKBENCH_COMMAND_PALETTE_ITEMS,
  ...TASK_COMMAND_PALETTE_ITEMS,
] as const);

export type CommandPaletteCommandId =
  (typeof COMMAND_PALETTE_CATALOG.items)[number]['command']['id'];
