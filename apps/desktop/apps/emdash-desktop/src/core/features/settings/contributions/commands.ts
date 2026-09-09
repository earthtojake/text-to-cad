import { defineCommand } from '@core/primitives/commands/api';
import { keybinding } from '@core/primitives/keybindings/api';

export const closeSettingsCommand = defineCommand({
  id: 'settings.close',
  title: 'Close Settings',
  description: 'Return to the previous view',
  category: 'Navigation',
  keybinding: keybinding.fixed('Escape'),
});

export const SETTINGS_COMMAND_DEFS = [closeSettingsCommand] as const;
