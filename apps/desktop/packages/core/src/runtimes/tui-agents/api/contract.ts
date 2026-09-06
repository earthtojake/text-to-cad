import { defineContract, fallible, liveLog, liveModel, liveState } from '@emdash/wire/rpc';
import { z } from 'zod';
import {
  tuiAgentStartInputSchema,
  tuiAgentStateListSchema,
  tuiInputErrorSchema,
  tuiResumeErrorSchema,
  tuiResumeOutcomeSchema,
  tuiSessionControlErrorSchema,
  tuiSessionListSchema,
  tuiStartErrorSchema,
  tuiStartOutcomeSchema,
} from './schemas';

const conv = z.object({ conversationId: z.string() });

export const tuiAgentsContract = defineContract({
  /**
   * Starts a fresh provider CLI agent session and resolves after PTY creation.
   *
   * If the process is already running or another launch won the race, this call
   * returns `attached` without replacing the active config.
   */
  start: fallible({
    input: tuiAgentStartInputSchema,
    data: z.object({ outcome: tuiStartOutcomeSchema }),
    error: tuiStartErrorSchema,
  }),

  /**
   * Resumes a provider CLI agent session and resolves after PTY creation.
   *
   * The server builds the provider command via `plugin.behavior.prompt.buildCommand(ctx)`.
   * Provider-native session id changes are published through the sessions LiveModel.
   * Missing provider session ids are downgraded to a fresh spawn and reported as
   * `fresh-fallback`.
   */
  resume: fallible({
    input: tuiAgentStartInputSchema,
    data: z.object({ outcome: tuiResumeOutcomeSchema }),
    error: tuiResumeErrorSchema,
  }),

  /**
   * Terminates the process; the persisted active intent survives, so the session
   * auto-resumes across daemon restarts. Retained output and last session state remain
   * available.
   */
  stop: fallible({
    input: conv,
    data: z.void(),
    error: tuiSessionControlErrorSchema,
  }),

  /**
   * Terminates any active process and removes the persisted active intent — no
   * auto-resume across daemon restarts. The conversation row remains available as an
   * inactive, manually resumable record.
   */
  kill: fallible({
    input: conv,
    data: z.void(),
    error: tuiSessionControlErrorSchema,
  }),

  /**
   * Kill plus purge: terminates any process, removes the persisted intent, and purges
   * retained output, session state, and agent state.
   */
  delete: fallible({
    input: conv,
    data: z.void(),
    error: tuiSessionControlErrorSchema,
  }),

  /**
   * Writes raw bytes into the PTY stdin.
   */
  sendInput: fallible({
    input: conv.extend({ data: z.string() }),
    data: z.void(),
    error: tuiInputErrorSchema,
  }),

  /**
   * Resizes the PTY window. Should be called whenever the terminal UI is resized.
   */
  resize: fallible({
    input: conv.extend({ cols: z.number().int(), rows: z.number().int() }),
    data: z.void(),
    error: tuiInputErrorSchema,
  }),

  /**
   * Streams PTY output for a session through a retained wire log.
   */
  output: liveLog({ key: conv }),

  /**
   * Reactive global session list (keyed by conversationId).
   * No key argument — one global model for all active PTY agent sessions.
   */
  sessions: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: tuiSessionListSchema }),
    },
  }),

  /**
   * Reactive global agent state list (keyed by conversationId).
   */
  agentStates: liveModel({
    key: z.void().optional(),
    states: {
      list: liveState({ data: tuiAgentStateListSchema }),
    },
  }),
});

export type TuiAgentsContract = typeof tuiAgentsContract;
