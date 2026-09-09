import { conversationsPaletteProviderDefs } from '@core/features/conversations/contributions/browser/conversation-palette-provider';
import { projectPaletteProviderDefs } from '@core/features/projects/contributions/browser/project-palette-provider';
import { taskPaletteProviderDefs } from '@core/features/tasks/contributions/browser/task-palette-provider';
import { workbenchCommandsPaletteProviderDefs } from '@core/features/workbench/contributions/browser/commands-palette-provider';
import { workbenchFilePaletteProviderDefs } from '@core/features/workbench/contributions/browser/file-palette-provider';
import { definePaletteProviderCatalog } from '@core/primitives/palette/api';

export const PALETTE_PROVIDER_CATALOG = definePaletteProviderCatalog([
  ...workbenchCommandsPaletteProviderDefs,
  ...taskPaletteProviderDefs,
  ...conversationsPaletteProviderDefs,
  ...workbenchFilePaletteProviderDefs,
  ...projectPaletteProviderDefs,
] as const);
