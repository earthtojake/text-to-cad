import { defineContract, fallible, liveLog, liveModel, liveState } from '@emdash/wire/rpc';
import { z } from 'zod';
import { terminalShellAvailabilityListSchema } from '#primitives/terminal-shell/api';
import {
  startTerminalInputSchema,
  killTmuxSessionsInputSchema,
  shellAvailabilityFailedErrorSchema,
  terminalControlInputSchema,
  terminalDataInputSchema,
  terminalKeySchema,
  terminalNotFoundErrorSchema,
  terminalResizeInputSchema,
  terminalRuntimeErrorSchema,
  terminalSessionListSchema,
  terminalStartFailedErrorSchema,
} from './schemas';

export const terminalsContract = defineContract({
  start: fallible({
    input: startTerminalInputSchema,
    data: z.void(),
    error: terminalStartFailedErrorSchema,
  }),
  getShellAvailability: fallible({
    input: z.void().optional(),
    data: terminalShellAvailabilityListSchema,
    error: shellAvailabilityFailedErrorSchema,
  }),
  output: liveLog({
    key: terminalKeySchema,
  }),
  sessions: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: terminalSessionListSchema }),
    },
  }),
  sendInput: fallible({
    input: terminalDataInputSchema,
    data: z.void(),
    error: terminalNotFoundErrorSchema,
  }),
  resize: fallible({
    input: terminalResizeInputSchema,
    data: z.void(),
    error: terminalNotFoundErrorSchema,
  }),
  kill: fallible({
    input: terminalControlInputSchema,
    data: z.void(),
    error: terminalNotFoundErrorSchema,
  }),
  killTmuxSessions: fallible({
    input: killTmuxSessionsInputSchema,
    data: z.void(),
    error: terminalRuntimeErrorSchema,
  }),
});

export type TerminalsContract = typeof terminalsContract;
