import {
  commandPaletteCommand,
  closeTabCommand,
  newProjectCommand,
  newTaskCommand,
  openInEditorCommand,
  nextTabCommand,
  previousTabCommand,
  renameTabCommand,
  reopenTabCommand,
  settingsCommand,
  splitPaneCommand,
  toggleLeftSidebarCommand,
  toggleThemeCommand,
  zenModeCommand,
} from '@core/features/workbench/contributions/commands';
import { defineCommandPaletteItem } from '@core/primitives/palette/api';

export const WORKBENCH_COMMAND_PALETTE_ITEMS = [
  defineCommandPaletteItem({ command: settingsCommand }),
  defineCommandPaletteItem({ command: newProjectCommand }),
  defineCommandPaletteItem({ command: newTaskCommand }),
  defineCommandPaletteItem({
    command: toggleThemeCommand,
    aliases: ['appearance', 'color scheme', 'dark mode', 'light mode'],
  }),
  defineCommandPaletteItem({ command: commandPaletteCommand }),
  defineCommandPaletteItem({ command: openInEditorCommand }),
  defineCommandPaletteItem({ command: toggleLeftSidebarCommand }),
  defineCommandPaletteItem({ command: zenModeCommand }),
  defineCommandPaletteItem({ command: nextTabCommand }),
  defineCommandPaletteItem({ command: previousTabCommand }),
  defineCommandPaletteItem({ command: closeTabCommand }),
  defineCommandPaletteItem({ command: reopenTabCommand }),
  defineCommandPaletteItem({ command: renameTabCommand }),
  defineCommandPaletteItem({ command: splitPaneCommand }),
] as const;
