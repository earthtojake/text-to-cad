import { z } from 'zod';
import { TERMINAL_SHELL_IDS, type TerminalShellAvailability } from './shell-ids';

export const terminalShellIdSchema = z.enum(TERMINAL_SHELL_IDS);

export const terminalShellAvailabilitySchema = z.object({
  id: terminalShellIdSchema,
  label: z.string(),
  isSystemDefault: z.boolean(),
  available: z.boolean(),
  reason: z.string().optional(),
}) satisfies z.ZodType<TerminalShellAvailability>;

export const terminalShellAvailabilityListSchema = z.array(terminalShellAvailabilitySchema);
