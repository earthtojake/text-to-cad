/**
 * The session state the UI renders, and the events that build it.
 *
 * `SessionState` is what `reduce.ts` folds ACP `session/update` notifications
 * (plus the handful of things the client itself knows: prompts it sent,
 * permission requests it answered, connection status) into. Main keeps one
 * per live session so it can hand a renderer a snapshot; the renderer runs
 * the same reducer on the event stream after that. Both sides agree because
 * both run this file.
 *
 * Everything is a zod schema so the IPC layer can validate a snapshot on its
 * way across the bridge. The ACP update itself is carried raw — validating
 * the agent's payload twice buys nothing, and the SDK already did it once.
 *
 * No Node, no Electron, no React: this module is shared by all three
 * processes and by the tests.
 */
import { z } from "zod";

/* -------------------------------------------------------------------------- */
/* Fragments of the ACP schema the state keeps                                 */
/* -------------------------------------------------------------------------- */

export const ToolKindSchema = z.enum([
  "read",
  "edit",
  "delete",
  "move",
  "search",
  "execute",
  "think",
  "fetch",
  "switch_mode",
  "other",
]);
export type ToolKind = z.infer<typeof ToolKindSchema>;

export const ToolCallStatusSchema = z.enum(["pending", "in_progress", "completed", "failed"]);
export type ToolCallStatus = z.infer<typeof ToolCallStatusSchema>;

/** What a tool call produced: prose, a diff, or a terminal it ran. */
export const ToolContentSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("text"), text: z.string() }),
  z.object({
    type: z.literal("image"),
    data: z.string(),
    mimeType: z.string(),
  }),
  z.object({
    type: z.literal("resource_link"),
    uri: z.string(),
    name: z.string(),
    mimeType: z.string().nullable().default(null),
  }),
  z.object({
    type: z.literal("diff"),
    path: z.string(),
    oldText: z.string().nullable(),
    newText: z.string(),
  }),
  z.object({ type: z.literal("terminal"), terminalId: z.string() }),
]);
export type ToolContent = z.infer<typeof ToolContentSchema>;

export const ToolLocationSchema = z.object({
  path: z.string(),
  line: z.number().int().nullable().default(null),
});
export type ToolLocation = z.infer<typeof ToolLocationSchema>;

export const PlanEntrySchema = z.object({
  content: z.string(),
  priority: z.enum(["high", "medium", "low"]),
  status: z.enum(["pending", "in_progress", "completed"]),
});
export type PlanEntry = z.infer<typeof PlanEntrySchema>;

export const PermissionOptionKindSchema = z.enum([
  "allow_once",
  "allow_always",
  "reject_once",
  "reject_always",
]);
export type PermissionOptionKind = z.infer<typeof PermissionOptionKindSchema>;

export const PermissionOptionSchema = z.object({
  optionId: z.string(),
  name: z.string(),
  kind: PermissionOptionKindSchema,
  /** The adapters' `_meta.permission.description`, when they send one. */
  description: z.string().nullable().default(null),
});
export type PermissionOption = z.infer<typeof PermissionOptionSchema>;

export const SessionModeSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().default(null),
  /**
   * The adapters' `_meta.kind`: `standard`, `plan`, `auto_review`,
   * `full_access`. It is how a provider names its own auto-approval preset
   * — Claude's `auto`, Codex's `agent` — without the app knowing either id
   * (`src/shared/acp/options.ts`).
   */
  kind: z.string().nullable().default(null),
});
export type SessionMode = z.infer<typeof SessionModeSchema>;

const ConfigOptionBase = {
  id: z.string(),
  name: z.string(),
  description: z.string().nullable().default(null),
  /** `mode`, `model`, `model_config`, `thought_level`, or anything the agent invents. */
  category: z.string().nullable().default(null),
};

export const ConfigOptionSchema = z.discriminatedUnion("type", [
  z.object({
    ...ConfigOptionBase,
    type: z.literal("select"),
    currentValue: z.string(),
    options: z.array(
      z.object({
        value: z.string(),
        name: z.string(),
        description: z.string().nullable().default(null),
        /** Set when the agent grouped its options (a model family, say). */
        group: z.string().nullable().default(null),
        /** `_meta.kind`, as on a session mode: the `mode` option carries it. */
        kind: z.string().nullable().default(null),
      }),
    ),
  }),
  z.object({
    ...ConfigOptionBase,
    type: z.literal("boolean"),
    currentValue: z.boolean(),
  }),
]);
export type ConfigOption = z.infer<typeof ConfigOptionSchema>;

export const AvailableCommandSchema = z.object({
  name: z.string(),
  description: z.string(),
  hint: z.string().nullable().default(null),
});
export type AvailableCommand = z.infer<typeof AvailableCommandSchema>;

/** `PromptResponse.usage`: what one turn cost. */
export const TurnUsageSchema = z.object({
  totalTokens: z.number(),
  inputTokens: z.number(),
  outputTokens: z.number(),
  thoughtTokens: z.number().nullable().default(null),
  cachedReadTokens: z.number().nullable().default(null),
  cachedWriteTokens: z.number().nullable().default(null),
});
export type TurnUsage = z.infer<typeof TurnUsageSchema>;

/** `usage_update`: how full the context window is. */
export const ContextUsageSchema = z.object({
  used: z.number(),
  size: z.number(),
  cost: z.object({ amount: z.number(), currency: z.string() }).nullable().default(null),
});
export type ContextUsage = z.infer<typeof ContextUsageSchema>;

export const StopReasonSchema = z.enum([
  "end_turn",
  "max_tokens",
  "max_turn_requests",
  "refusal",
  "cancelled",
]);
export type StopReason = z.infer<typeof StopReasonSchema>;

export const SubagentStateSchema = z.enum([
  "running",
  "completed",
  "failed",
  "cancelled",
  "disconnected",
]);
export type SubagentState = z.infer<typeof SubagentStateSchema>;

/** What the user can put in the composer: the ACP content blocks we send. */
export const PromptBlockSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("text"), text: z.string() }),
  z.object({
    type: z.literal("image"),
    data: z.string(),
    mimeType: z.string(),
    uri: z.string().nullable().default(null),
  }),
  z.object({
    type: z.literal("resource_link"),
    uri: z.string(),
    name: z.string(),
    mimeType: z.string().nullable().default(null),
    title: z.string().nullable().default(null),
  }),
  /** An attached text file, embedded: the agent gets the content, not a path it may not be able to read. */
  z.object({
    type: z.literal("resource"),
    uri: z.string(),
    text: z.string(),
    mimeType: z.string().nullable().default(null),
  }),
]);
export type PromptBlock = z.infer<typeof PromptBlockSchema>;

/* -------------------------------------------------------------------------- */
/* Parts and turns                                                              */
/* -------------------------------------------------------------------------- */

/**
 * One thing in a turn. Text and thoughts accumulate as chunks stream in; tool
 * calls upsert by id; the others are single events.
 *
 * `subagent` and `tool_call.children` both hold nested parts. The first is
 * the draft native-subagent lifecycle (`subagent_spawned` /
 * `subagent_state_update`, child updates arriving under the child session
 * id); the second is the Claude adapter's flattened form, where the child's
 * activity arrives on the root session tagged `_meta.claudeCode.parentToolUseId`.
 */
export type Part =
  | { type: "text"; text: string }
  | { type: "thought"; text: string }
  | {
      type: "tool_call";
      id: string;
      kind: ToolKind;
      title: string;
      /** The agent-side tool name (`Bash`, `Edit`), when the adapter sends it. */
      name: string | null;
      status: ToolCallStatus;
      input: unknown;
      output: unknown;
      content: ToolContent[];
      locations: ToolLocation[];
      /**
       * Text the adapter streamed for this call while it ran — Codex's
       * `_meta.terminal_output_delta` — so a command's output shows before
       * the call completes. Empty for adapters that only report at the end.
       */
      stream: string;
      children: Part[];
    }
  | { type: "plan"; entries: PlanEntry[] }
  | {
      type: "permission_request";
      requestId: string;
      toolCallId: string;
      title: string | null;
      description: string | null;
      options: PermissionOption[];
      outcome: { state: "pending" } | { state: "selected"; optionId: string } | { state: "cancelled" };
    }
  | {
      type: "subagent";
      sessionId: string;
      name: string;
      task: string | null;
      state: SubagentState;
      parts: Part[];
    }
  | { type: "mode_change"; modeId: string }
  | { type: "available_commands"; commands: AvailableCommand[] }
  | { type: "usage"; usage: TurnUsage }
  | { type: "error"; message: string }
  | { type: "image"; data: string; mimeType: string }
  | { type: "resource_link"; uri: string; name: string };

const PermissionOutcomeSchema = z.discriminatedUnion("state", [
  z.object({ state: z.literal("pending") }),
  z.object({ state: z.literal("selected"), optionId: z.string() }),
  z.object({ state: z.literal("cancelled") }),
]);

export const PartSchema: z.ZodType<Part> = z.lazy(() =>
  z.discriminatedUnion("type", [
    z.object({ type: z.literal("text"), text: z.string() }),
    z.object({ type: z.literal("thought"), text: z.string() }),
    z.object({
      type: z.literal("tool_call"),
      id: z.string(),
      kind: ToolKindSchema,
      title: z.string(),
      name: z.string().nullable(),
      status: ToolCallStatusSchema,
      input: z.unknown(),
      output: z.unknown(),
      content: z.array(ToolContentSchema),
      locations: z.array(ToolLocationSchema),
      stream: z.string(),
      children: z.array(PartSchema),
    }),
    z.object({ type: z.literal("plan"), entries: z.array(PlanEntrySchema) }),
    z.object({
      type: z.literal("permission_request"),
      requestId: z.string(),
      toolCallId: z.string(),
      title: z.string().nullable(),
      description: z.string().nullable(),
      options: z.array(PermissionOptionSchema),
      outcome: PermissionOutcomeSchema,
    }),
    z.object({
      type: z.literal("subagent"),
      sessionId: z.string(),
      name: z.string(),
      task: z.string().nullable(),
      state: SubagentStateSchema,
      parts: z.array(PartSchema),
    }),
    z.object({ type: z.literal("mode_change"), modeId: z.string() }),
    z.object({ type: z.literal("available_commands"), commands: z.array(AvailableCommandSchema) }),
    z.object({ type: z.literal("usage"), usage: TurnUsageSchema }),
    z.object({ type: z.literal("error"), message: z.string() }),
    z.object({ type: z.literal("image"), data: z.string(), mimeType: z.string() }),
    z.object({ type: z.literal("resource_link"), uri: z.string(), name: z.string() }),
  ]),
);

export type ToolCallPart = Extract<Part, { type: "tool_call" }>;
export type SubagentPart = Extract<Part, { type: "subagent" }>;
export type PermissionRequestPart = Extract<Part, { type: "permission_request" }>;

export const TurnSchema = z.object({
  id: z.string(),
  role: z.enum(["user", "agent"]),
  parts: z.array(PartSchema),
  startedAt: z.number(),
  /** Null while the turn is open — streaming, or being replayed by `session/load`. */
  endedAt: z.number().nullable(),
  stopReason: StopReasonSchema.nullable(),
});
export type Turn = z.infer<typeof TurnSchema>;

/* -------------------------------------------------------------------------- */
/* The state                                                                    */
/* -------------------------------------------------------------------------- */

export const LiveStatusSchema = z.enum([
  "connecting",
  "idle",
  "running",
  "waiting",
  "error",
  "closed",
]);
export type LiveStatus = z.infer<typeof LiveStatusSchema>;

export const ApprovalModeSchema = z.enum(["ask", "approve-for-me"]);
export type ApprovalMode = z.infer<typeof ApprovalModeSchema>;

/** A permission request the user has not answered yet. */
export const PendingPermissionSchema = z.object({
  requestId: z.string(),
  /** The ACP session the request came in on (a child session for subagents). */
  acpSessionId: z.string(),
  toolCallId: z.string(),
  title: z.string().nullable(),
  description: z.string().nullable(),
  kind: ToolKindSchema.nullable(),
  input: z.unknown(),
  options: z.array(PermissionOptionSchema),
});
export type PendingPermission = z.infer<typeof PendingPermissionSchema>;

export const SessionStateSchema = z.object({
  /** The app's session id (the sqlite row), not the agent's. */
  sessionId: z.string(),
  agentId: z.string(),
  /** The agent's id for the session; null until `session/new` answers. */
  acpSessionId: z.string().nullable(),
  status: LiveStatusSchema,
  /** Set while `status` is `error`. */
  error: z.string().nullable(),
  approvalMode: ApprovalModeSchema,
  /** From `session_info_update`; the sidebar prefers the first prompt. */
  title: z.string().nullable(),
  turns: z.array(TurnSchema),
  currentModeId: z.string().nullable(),
  modes: z.array(SessionModeSchema),
  configOptions: z.array(ConfigOptionSchema),
  availableCommands: z.array(AvailableCommandSchema),
  /** The latest plan the agent reported, or null once it removed it. */
  plan: z.array(PlanEntrySchema).nullable(),
  contextUsage: ContextUsageSchema.nullable(),
  lastTurnUsage: TurnUsageSchema.nullable(),
  pendingPermissions: z.array(PendingPermissionSchema),
  /** Every subagent session id seen, mapped to the root session's part path. */
  subagentSessionIds: z.array(z.string()),
});
export type SessionState = z.infer<typeof SessionStateSchema>;

export function initialSessionState(sessionId: string, agentId: string): SessionState {
  return {
    sessionId,
    agentId,
    acpSessionId: null,
    status: "connecting",
    error: null,
    approvalMode: "ask",
    title: null,
    turns: [],
    currentModeId: null,
    modes: [],
    configOptions: [],
    availableCommands: [],
    plan: null,
    contextUsage: null,
    lastTurnUsage: null,
    pendingPermissions: [],
    subagentSessionIds: [],
  };
}

/* -------------------------------------------------------------------------- */
/* Events                                                                       */
/* -------------------------------------------------------------------------- */

/**
 * A raw ACP `session/update` payload. Kept loose on purpose: the reducer
 * reads the fields it knows and ignores the rest, which is what lets it
 * accept draft update kinds the SDK's own schema does not have yet.
 */
export const RawSessionUpdateSchema = z.looseObject({ sessionUpdate: z.string() });
export type RawSessionUpdate = z.infer<typeof RawSessionUpdateSchema>;

/**
 * Everything the reducer folds. `session/update` is the agent talking; the
 * rest is the client narrating what it did or learned.
 */
export const SessionEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("session/update"),
    /** The ACP session id the notification arrived under. */
    acpSessionId: z.string(),
    update: RawSessionUpdateSchema,
    at: z.number(),
  }),
  /** `session/new` or `session/load` answered. */
  z.object({
    type: z.literal("session/connected"),
    acpSessionId: z.string(),
    modes: z
      .object({ currentModeId: z.string(), availableModes: z.array(SessionModeSchema) })
      .nullable(),
    configOptions: z.array(ConfigOptionSchema).nullable(),
    /** True for `session/load`: replayed history until `session/loaded`. */
    loading: z.boolean(),
    at: z.number(),
  }),
  /** `session/load` finished replaying. */
  z.object({ type: z.literal("session/loaded"), at: z.number() }),
  z.object({
    type: z.literal("prompt/start"),
    turnId: z.string(),
    content: z.array(PromptBlockSchema),
    at: z.number(),
  }),
  z.object({
    type: z.literal("prompt/end"),
    stopReason: StopReasonSchema,
    usage: TurnUsageSchema.nullable(),
    at: z.number(),
  }),
  z.object({ type: z.literal("prompt/error"), message: z.string(), at: z.number() }),
  z.object({
    type: z.literal("permission/request"),
    request: PendingPermissionSchema,
    at: z.number(),
  }),
  z.object({
    type: z.literal("permission/resolve"),
    requestId: z.string(),
    outcome: PermissionOutcomeSchema,
    at: z.number(),
  }),
  z.object({
    type: z.literal("config/updated"),
    configOptions: z.array(ConfigOptionSchema),
    at: z.number(),
  }),
  z.object({
    type: z.literal("status"),
    status: LiveStatusSchema,
    error: z.string().nullable(),
    at: z.number(),
  }),
  z.object({ type: z.literal("approval"), mode: ApprovalModeSchema, at: z.number() }),
]);
export type SessionEvent = z.infer<typeof SessionEventSchema>;
