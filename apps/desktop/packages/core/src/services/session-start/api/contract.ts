import { defineContract, fallible } from '@emdash/wire/rpc';
import {
  acpSessionStartInputSchema,
  acpSessionStartResultSchema,
  sessionStartErrorSchema,
  tuiSessionStartInputSchema,
  tuiSessionStartResultSchema,
} from './schemas';

export const acpSessionStartContract = defineContract({
  start: fallible({
    input: acpSessionStartInputSchema,
    data: acpSessionStartResultSchema,
    error: sessionStartErrorSchema,
  }),
});

export const tuiSessionStartContract = defineContract({
  start: fallible({
    input: tuiSessionStartInputSchema,
    data: tuiSessionStartResultSchema,
    error: sessionStartErrorSchema,
  }),
});

export type AcpSessionStartContract = typeof acpSessionStartContract;
export type TuiSessionStartContract = typeof tuiSessionStartContract;
