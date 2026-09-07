/**
 * `sessions.*`: the session index plus the live ACP connection behind each
 * row, and the events that carry a session's state to the renderer.
 *
 * The renderer never sees the connection. It asks for a session to be
 * created or loaded, sends prompts, answers permission requests — and folds
 * `session.update` through the same reducer main runs (`src/shared/acp`).
 */
import { z } from "zod";

import {
  ApprovalModeSchema,
  PendingPermissionSchema,
  PromptBlockSchema,
  SessionEventSchema,
  SessionStateSchema,
} from "../acp/types";
import { GitModeSchema, SessionSchema, SessionStatusSchema } from "../types";
import { invoke } from "./define";

const Id = z.object({ id: z.string().min(1) });

export const acpContract = {
  sessions: {
    /** Every session, or just one project's, newest first. */
    list: invoke(z.object({ projectId: z.string().optional() }), z.array(SessionSchema)),
    get: invoke(Id, SessionSchema.nullable()),
    /**
     * Spawn the agent, `initialize`, `session/new`. Answers once the agent has
     * a session id; the state snapshot follows on `session.state`.
     *
     * The working directory is **not** given: main resolves it from
     * `gitMode` (plan §9), which is the only place that knows where worktrees
     * go and what they are called. `cwd` is the one exception — Settings'
     * `New chat in this worktree` — and main checks it belongs to the project
     * before running anything in it.
     */
    create: invoke(
      z.object({
        projectId: z.string().min(1),
        agentId: z.string().min(1),
        /** Omitted means the `defaultGitMode` setting. */
        gitMode: GitModeSchema.optional(),
        /** The first prompt, when there is one: a worktree's name comes from it. */
        name: z.string().optional(),
        /** An existing worktree of this project, or the project itself. */
        cwd: z.string().min(1).optional(),
      }),
      SessionSchema,
    ),
    /** Reconnect a session from the index: spawn the agent and `session/load`. */
    load: invoke(Id, SessionStateSchema),
    /** The current state snapshot of a live session, or null when it is not connected. */
    state: invoke(Id, SessionStateSchema.nullable()),
    /**
     * Send a prompt. Resolves when the turn ends (the whole turn streams on
     * `session.update` in the meantime), with the agent's stop reason.
     */
    prompt: invoke(
      Id.extend({ content: z.array(PromptBlockSchema).min(1) }),
      z.object({ stopReason: z.string() }),
    ),
    cancel: invoke(Id, z.void()),
    setMode: invoke(Id.extend({ modeId: z.string().min(1) }), z.void()),
    setConfigOption: invoke(
      Id.extend({ configId: z.string().min(1), value: z.union([z.string(), z.boolean()]) }),
      z.void(),
    ),
    respondPermission: invoke(
      Id.extend({
        requestId: z.string().min(1),
        /** Null cancels the request instead of picking an option. */
        optionId: z.string().nullable(),
      }),
      z.void(),
    ),
    setApprovalMode: invoke(Id.extend({ mode: ApprovalModeSchema }), z.void()),
    /** The sidebar title. Set by the first prompt (Codex's convention) until the user renames. */
    rename: invoke(Id.extend({ title: z.string().min(1).max(200) }), SessionSchema),
    /** Hide from (or restore to) the sidebar. Archiving closes the adapter. */
    archive: invoke(Id.extend({ archived: z.boolean() }), SessionSchema),
    /** Kill the adapter; the index row stays and `load` brings it back. */
    close: invoke(Id, z.void()),
    /** Close and forget. The agent's own transcript store is not touched. */
    delete: invoke(Id, z.void()),
  },
} as const;

export const acpEvents = {
  /** One reducer event for one session — a raw ACP update, or the client's own narration. */
  "session.update": z.object({ sessionId: z.string(), event: SessionEventSchema }),
  /** A full snapshot, sent when a session connects or loads. */
  "session.state": z.object({ sessionId: z.string(), state: SessionStateSchema }),
  /** The index row's status changed (mirrors `sessions.changed` for one row). */
  "session.status": z.object({
    sessionId: z.string(),
    status: SessionStatusSchema,
    error: z.string().nullable(),
  }),
  /** The agent is blocked on the user; the options are the agent's, verbatim. */
  "session.permission": z.object({ sessionId: z.string(), request: PendingPermissionSchema }),
  /** A chunk from an agent-created terminal. */
  "terminal.output": z.object({
    sessionId: z.string(),
    terminalId: z.string(),
    data: z.string(),
    /** Set once on exit. */
    exit: z.object({ exitCode: z.number().nullable(), signal: z.string().nullable() }).nullable(),
  }),
  /** The agent wrote files through `fs/write_text_file`; the explorer should refresh them. */
  "files.changed": z.object({ sessionId: z.string(), paths: z.array(z.string()) }),
} as const;
