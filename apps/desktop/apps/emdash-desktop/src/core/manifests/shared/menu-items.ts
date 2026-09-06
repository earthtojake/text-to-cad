import {
  closeTabCommand,
  commandPaletteCommand,
  settingsCommand,
} from '@core/features/workbench/contributions/commands';

export const MENU_ITEMS = [settingsCommand, closeTabCommand, commandPaletteCommand] as const;
