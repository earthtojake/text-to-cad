import { TERMINAL_SHELL_IDS } from '@emdash/core/primitives/terminal-shell/api';
import { z } from 'zod';
import type { TerminalSettings } from '@core/primitives/app-settings/api';
import { defineSettingsContribution } from '@core/primitives/settings/api';
import {
  TERMINAL_FONT_SIZE_DEFAULT,
  TERMINAL_FONT_SIZE_MAX,
  TERMINAL_FONT_SIZE_MIN,
} from '@core/primitives/terminals/api';

const terminalSettingsSchema = z.object({
  fontFamily: z.string().optional(),
  fontSize: z.number().min(TERMINAL_FONT_SIZE_MIN).max(TERMINAL_FONT_SIZE_MAX).optional(),
  autoCopyOnSelection: z.boolean(),
  macOptionIsMeta: z.boolean(),
  defaultShell: z.enum(TERMINAL_SHELL_IDS),
});

export const terminalSettingsContribution = defineSettingsContribution<
  'terminal',
  TerminalSettings
>({
  key: 'terminal',
  schema: terminalSettingsSchema,
  defaults: {
    fontSize: TERMINAL_FONT_SIZE_DEFAULT,
    autoCopyOnSelection: false,
    macOptionIsMeta: false,
    defaultShell: 'system',
  },
});
