/**
 * The one piece of protocol logic in the app: fold a stream of events into a
 * `SessionState` (plan §5).
 *
 * Pure. No clock (every event carries `at`), no ids drawn from randomness
 * (turn ids the reducer mints are positional), no mutation of the input —
 * the renderer's store relies on fresh references to know what changed, and
 * the tests replay recorded adapter transcripts through it.
 *
 * Rules the adapters made necessary, learned from the recordings under
 * `tests/fixtures/acp/`:
 *
 *   - Text and thought chunks concatenate into the trailing part of the same
 *     kind; a tool call in between starts a new one.
 *   - Tool calls upsert by id. A `tool_call_update` for an id nobody
 *     announced is created rather than dropped: better a row with a blank
 *     title than a permission request pointing at nothing.
 *   - An update whose `sessionId` is a subagent's lands inside that
 *     subagent's part. The Claude adapter's flattened form tags updates with
 *     `_meta.claudeCode.parentToolUseId` instead; those land in the parent
 *     tool call's `children`.
 *   - Session-level facts (mode, config options, commands, usage, title)
 *     always update the state; they only become parts when a turn is open,
 *     because the adapters send most of them right after `session/new`.
 */
import {
  type AvailableCommand,
  type ConfigOption,
  type Part,
  type PendingPermission,
  type PermissionOption,
  type PlanEntry,
  type PromptBlock,
  type RawSessionUpdate,
  type SessionEvent,
  type SessionMode,
  type SessionState,
  type SubagentState,
  type ToolCallPart,
  type ToolCallStatus,
  type ToolContent,
  type ToolKind,
  type ToolLocation,
  type Turn,
  ToolCallStatusSchema,
  ToolKindSchema,
} from "./types";

/* -------------------------------------------------------------------------- */
/* Entry point                                                                  */
/* -------------------------------------------------------------------------- */

export function reduce(state: SessionState, event: SessionEvent): SessionState {
  switch (event.type) {
    case "session/update":
      return applyUpdate(state, event.acpSessionId, event.update, event.at);

    case "session/connected":
      return {
        ...state,
        acpSessionId: event.acpSessionId,
        status: event.loading ? "connecting" : "idle",
        error: null,
        currentModeId: event.modes?.currentModeId ?? state.currentModeId,
        modes: event.modes?.availableModes ?? state.modes,
        configOptions: event.configOptions ?? state.configOptions,
      };

    case "session/loaded":
      return { ...closeOpenTurn(state, event.at, null), status: "idle" };

    case "prompt/start": {
      const closed = closeOpenTurn(state, event.at, null);
      const userTurn: Turn = {
        id: event.turnId,
        role: "user",
        parts: event.content.map(promptBlockToPart),
        startedAt: event.at,
        endedAt: event.at,
        stopReason: null,
      };
      const agentTurn: Turn = {
        id: `${event.turnId}:agent`,
        role: "agent",
        parts: [],
        startedAt: event.at,
        endedAt: null,
        stopReason: null,
      };
      return {
        ...closed,
        turns: [...closed.turns, userTurn, agentTurn],
        status: "running",
        error: null,
      };
    }

    case "prompt/end": {
      let next = state;
      if (event.usage) {
        next = withRootParts(next, event.at, (parts) => [
          ...parts,
          { type: "usage", usage: event.usage! },
        ]);
      }
      next = closeOpenTurn(next, event.at, event.stopReason);
      return {
        ...next,
        status: "idle",
        lastTurnUsage: event.usage ?? next.lastTurnUsage,
        // A cancelled turn takes its unanswered permission requests with it.
        pendingPermissions: [],
      };
    }

    case "prompt/error": {
      const withError = withRootParts(state, event.at, (parts) => [
        ...parts,
        { type: "error", message: event.message },
      ]);
      return {
        ...closeOpenTurn(withError, event.at, null),
        status: "error",
        error: event.message,
        pendingPermissions: [],
      };
    }

    case "permission/request": {
      const { request } = event;
      const part: Part = {
        type: "permission_request",
        requestId: request.requestId,
        toolCallId: request.toolCallId,
        title: request.title,
        description: request.description,
        options: request.options,
        outcome: { state: "pending" },
      };
      const next = withSessionParts(state, request.acpSessionId, event.at, (parts) => [
        ...parts,
        part,
      ]);
      return {
        ...next,
        status: "waiting",
        pendingPermissions: [...next.pendingPermissions, request],
      };
    }

    case "permission/resolve": {
      const pendingPermissions = state.pendingPermissions.filter(
        (pending) => pending.requestId !== event.requestId,
      );
      const turns = state.turns.map((turn) => ({
        ...turn,
        parts: mapPartsDeep(turn.parts, (part) =>
          part.type === "permission_request" && part.requestId === event.requestId
            ? { ...part, outcome: event.outcome }
            : part,
        ),
      }));
      return {
        ...state,
        turns,
        pendingPermissions,
        status:
          state.status === "waiting" && pendingPermissions.length === 0 ? "running" : state.status,
      };
    }

    case "config/updated":
      return { ...state, configOptions: event.configOptions };

    case "status":
      return { ...state, status: event.status, error: event.error };

    case "approval":
      return { ...state, approvalMode: event.mode };
  }
}

/* -------------------------------------------------------------------------- */
/* session/update                                                               */
/* -------------------------------------------------------------------------- */

function applyUpdate(
  state: SessionState,
  acpSessionId: string,
  update: RawSessionUpdate,
  at: number,
): SessionState {
  const u = update as Record<string, unknown>;
  switch (update.sessionUpdate) {
    case "user_message_chunk": {
      const part = contentBlockToPart(u.content);
      return part ? appendUserChunk(state, at, part) : state;
    }

    case "agent_message_chunk":
    case "agent_thought_chunk": {
      const part = contentBlockToPart(u.content, update.sessionUpdate === "agent_thought_chunk");
      if (!part) {
        return state;
      }
      return withUpdateTarget(state, acpSessionId, u, at, (parts) => appendChunk(parts, part));
    }

    case "tool_call":
    case "tool_call_update": {
      const id = asString(u.toolCallId);
      if (!id) {
        return state;
      }
      return withUpdateTarget(state, acpSessionId, u, at, (parts) => upsertToolCall(parts, id, u));
    }

    case "plan": {
      const entries = planEntries(u.entries);
      const next = { ...state, plan: entries };
      return hasOpenAgentTurn(next)
        ? withSessionParts(next, acpSessionId, at, (parts) => setPlan(parts, entries), false)
        : next;
    }

    case "plan_update": {
      const plan = asRecord(u.plan);
      if (plan?.type !== "items") {
        return state;
      }
      const entries = planEntries(plan.entries);
      const next = { ...state, plan: entries };
      return hasOpenAgentTurn(next)
        ? withSessionParts(next, acpSessionId, at, (parts) => setPlan(parts, entries), false)
        : next;
    }

    case "plan_removed":
      return { ...state, plan: null };

    case "available_commands_update": {
      const commands = availableCommands(u.availableCommands);
      const next = { ...state, availableCommands: commands };
      return hasOpenAgentTurn(next)
        ? withSessionParts(
            next,
            acpSessionId,
            at,
            (parts) => [...parts, { type: "available_commands", commands }],
            false,
          )
        : next;
    }

    case "current_mode_update": {
      const modeId = asString(u.currentModeId);
      if (!modeId) {
        return state;
      }
      const next = { ...state, currentModeId: modeId };
      return hasOpenAgentTurn(next)
        ? withSessionParts(
            next,
            acpSessionId,
            at,
            (parts) => [...parts, { type: "mode_change", modeId }],
            false,
          )
        : next;
    }

    case "config_option_update":
      return { ...state, configOptions: configOptions(u.configOptions) };

    case "session_info_update": {
      const title = asString(u.title);
      return title === null ? state : { ...state, title };
    }

    case "usage_update": {
      const used = asNumber(u.used);
      const size = asNumber(u.size);
      if (used === null || size === null) {
        return state;
      }
      const cost = asRecord(u.cost);
      const amount = cost ? asNumber(cost.amount) : null;
      const currency = cost ? asString(cost.currency) : null;
      return {
        ...state,
        contextUsage: {
          used,
          size,
          cost: amount !== null && currency !== null ? { amount, currency } : null,
        },
      };
    }

    case "subagent_spawned": {
      const childId = asString(u.subagentSessionId) ?? asString(u.sessionId);
      if (!childId) {
        return state;
      }
      const part: Part = {
        type: "subagent",
        sessionId: childId,
        name: asString(u.name) ?? asString(u.title) ?? asString(u.subagentType) ?? "Subagent",
        task: asString(u.task) ?? asString(u.description) ?? asString(u.prompt),
        state: "running",
      parts: [],
      };
      const next = withSessionParts(state, acpSessionId, at, (parts) =>
        findSubagent(parts, childId) ? parts : [...parts, part],
      );
      return {
        ...next,
        subagentSessionIds: next.subagentSessionIds.includes(childId)
          ? next.subagentSessionIds
          : [...next.subagentSessionIds, childId],
      };
    }

    case "subagent_state_update": {
      const childId = asString(u.subagentSessionId) ?? asString(u.sessionId);
      if (!childId) {
        return state;
      }
      const subagentState = toSubagentState(u.state ?? u.status);
      return {
        ...state,
        turns: state.turns.map((turn) => ({
          ...turn,
          parts: mapPartsDeep(turn.parts, (part) =>
            part.type === "subagent" && part.sessionId === childId
              ? { ...part, state: subagentState }
              : part,
          ),
        })),
      };
    }

    default:
      // compaction_update, compaction_summary_chunk, and whatever an adapter
      // invents next: nothing the transcript shows.
      return state;
  }
}

/* -------------------------------------------------------------------------- */
/* Turn plumbing                                                               */
/* -------------------------------------------------------------------------- */

function hasOpenAgentTurn(state: SessionState): boolean {
  const last = state.turns.at(-1);
  return last?.role === "agent" && last.endedAt === null;
}

function closeOpenTurn(state: SessionState, at: number, stopReason: Turn["stopReason"]) {
  const last = state.turns.at(-1);
  if (!last || last.endedAt !== null) {
    return state;
  }
  const closed: Turn = { ...last, endedAt: at, stopReason };
  return { ...state, turns: [...state.turns.slice(0, -1), closed] };
}

/**
 * Apply `fn` to the open agent turn's parts, opening a turn if there is none
 * (a replayed history has no `prompt/start`). When `create` is false and no
 * agent turn is open, the state comes back unchanged.
 */
function withRootParts(
  state: SessionState,
  at: number,
  fn: (parts: Part[]) => Part[],
  create = true,
): SessionState {
  const last = state.turns.at(-1);
  if (last?.role === "agent" && last.endedAt === null) {
    const updated: Turn = { ...last, parts: fn(last.parts) };
    return { ...state, turns: [...state.turns.slice(0, -1), updated] };
  }
  if (!create) {
    return state;
  }
  const closed = closeOpenTurn(state, at, null);
  const turn: Turn = {
    id: `t${closed.turns.length + 1}`,
    role: "agent",
    parts: fn([]),
    startedAt: at,
    endedAt: null,
    stopReason: null,
  };
  return { ...closed, turns: [...closed.turns, turn] };
}

/** Route by ACP session id: the root's open turn, or a subagent's parts. */
function withSessionParts(
  state: SessionState,
  acpSessionId: string,
  at: number,
  fn: (parts: Part[]) => Part[],
  create = true,
): SessionState {
  if (acpSessionId !== state.acpSessionId && state.subagentSessionIds.includes(acpSessionId)) {
    let found = false;
    const turns = state.turns.map((turn) => {
      const parts = mapPartsDeep(turn.parts, (part) => {
        if (part.type === "subagent" && part.sessionId === acpSessionId) {
          found = true;
          return { ...part, parts: fn(part.parts) };
        }
        return part;
      });
      return parts === turn.parts ? turn : { ...turn, parts };
    });
    if (found) {
      return { ...state, turns };
    }
  }
  return withRootParts(state, at, fn, create);
}

/** Route by session id, then by the Claude adapter's parent-tool tag. */
function withUpdateTarget(
  state: SessionState,
  acpSessionId: string,
  update: Record<string, unknown>,
  at: number,
  fn: (parts: Part[]) => Part[],
): SessionState {
  const parentId = claudeParentToolUseId(update);
  if (!parentId) {
    return withSessionParts(state, acpSessionId, at, fn);
  }
  let found = false;
  const turns = state.turns.map((turn) => {
    const parts = mapPartsDeep(turn.parts, (part) => {
      if (part.type === "tool_call" && part.id === parentId) {
        found = true;
        return { ...part, children: fn(part.children) };
      }
      return part;
    });
    return parts === turn.parts ? turn : { ...turn, parts };
  });
  return found ? { ...state, turns } : withSessionParts(state, acpSessionId, at, fn);
}

function claudeParentToolUseId(update: Record<string, unknown>): string | null {
  const meta = asRecord(update._meta);
  const claude = meta ? asRecord(meta.claudeCode) : null;
  return claude ? asString(claude.parentToolUseId) : null;
}

function appendUserChunk(state: SessionState, at: number, part: Part): SessionState {
  const last = state.turns.at(-1);
  if (last?.role === "user" && last.endedAt === null) {
    const updated: Turn = { ...last, parts: appendChunk(last.parts, part) };
    return { ...state, turns: [...state.turns.slice(0, -1), updated] };
  }
  const closed = closeOpenTurn(state, at, null);
  const turn: Turn = {
    id: `t${closed.turns.length + 1}`,
    role: "user",
    parts: [part],
    startedAt: at,
    endedAt: null,
    stopReason: null,
  };
  return { ...closed, turns: [...closed.turns, turn] };
}

/* -------------------------------------------------------------------------- */
/* Part-level operations                                                       */
/* -------------------------------------------------------------------------- */

/** Text onto trailing text, thought onto trailing thought; anything else appends. */
function appendChunk(parts: Part[], part: Part): Part[] {
  const last = parts.at(-1);
  if (
    last &&
    (part.type === "text" || part.type === "thought") &&
    last.type === part.type
  ) {
    return [...parts.slice(0, -1), { ...last, text: last.text + part.text }];
  }
  return [...parts, part];
}

function setPlan(parts: Part[], entries: PlanEntry[]): Part[] {
  const index = parts.findLastIndex((part) => part.type === "plan");
  if (index === -1) {
    return [...parts, { type: "plan", entries }];
  }
  return parts.map((part, i) => (i === index ? { type: "plan", entries } : part));
}

function upsertToolCall(parts: Part[], id: string, update: Record<string, unknown>): Part[] {
  let found = false;
  const next = mapPartsDeep(parts, (part) => {
    if (part.type === "tool_call" && part.id === id) {
      found = true;
      return mergeToolCall(part, update);
    }
    return part;
  });
  return found ? next : [...parts, mergeToolCall(blankToolCall(id), update)];
}

function blankToolCall(id: string): ToolCallPart {
  return {
    type: "tool_call",
    id,
    kind: "other",
    title: "",
    name: null,
    status: "pending",
    input: undefined,
    output: undefined,
    content: [],
    locations: [],
    stream: "",
    children: [],
  };
}

/** Fields the update carries replace; fields it omits (or nulls) survive. */
function mergeToolCall(part: ToolCallPart, update: Record<string, unknown>): ToolCallPart {
  const kind = toolKind(update.kind);
  const status = toolStatus(update.status);
  const title = asString(update.title);
  const name = asString(update.name);
  const content = Array.isArray(update.content) ? toolContents(update.content) : null;
  const locations = Array.isArray(update.locations) ? toolLocations(update.locations) : null;
  const delta = streamedOutput(update);
  return {
    ...part,
    kind: kind ?? part.kind,
    status: status ?? part.status,
    title: title ?? part.title ?? name ?? part.name ?? "",
    name: name ?? part.name,
    input: update.rawInput !== undefined ? update.rawInput : part.input,
    output: update.rawOutput !== undefined ? update.rawOutput : part.output,
    content: content ?? part.content,
    locations: locations ?? part.locations,
    stream: delta === null ? part.stream : part.stream + delta,
  };
}

/** Codex streams a command's output as `_meta.terminal_output_delta.data` on each update. */
function streamedOutput(update: Record<string, unknown>): string | null {
  const meta = asRecord(update._meta);
  const delta = meta ? asRecord(meta.terminal_output_delta) : null;
  return delta ? asString(delta.data) : null;
}

/** Rebuild a parts tree with `fn` applied to every node, preserving identity where nothing changed. */
function mapPartsDeep(parts: Part[], fn: (part: Part) => Part): Part[] {
  let changed = false;
  const next = parts.map((part) => {
    let inner = part;
    if (part.type === "tool_call" && part.children.length > 0) {
      const children = mapPartsDeep(part.children, fn);
      if (children !== part.children) {
        inner = { ...part, children };
      }
    } else if (part.type === "subagent" && part.parts.length > 0) {
      const nested = mapPartsDeep(part.parts, fn);
      if (nested !== part.parts) {
        inner = { ...part, parts: nested };
      }
    }
    const mapped = fn(inner);
    if (mapped !== part) {
      changed = true;
    }
    return mapped;
  });
  return changed ? next : parts;
}

function findSubagent(parts: Part[], sessionId: string): boolean {
  return parts.some(
    (part) =>
      (part.type === "subagent" && (part.sessionId === sessionId || findSubagent(part.parts, sessionId))) ||
      (part.type === "tool_call" && findSubagent(part.children, sessionId)),
  );
}

/* -------------------------------------------------------------------------- */
/* Conversions from the wire                                                   */
/* -------------------------------------------------------------------------- */

function promptBlockToPart(block: PromptBlock): Part {
  switch (block.type) {
    case "text":
      return { type: "text", text: block.text };
    case "image":
      return { type: "image", data: block.data, mimeType: block.mimeType };
    case "resource_link":
      return { type: "resource_link", uri: block.uri, name: block.name };
    case "resource":
      return { type: "resource_link", uri: block.uri, name: block.uri.split(/[\\/]/).pop() || block.uri };
  }
}

function contentBlockToPart(raw: unknown, thought = false): Part | null {
  const block = asRecord(raw);
  if (!block) {
    return null;
  }
  switch (block.type) {
    case "text": {
      const text = asString(block.text);
      return text === null ? null : { type: thought ? "thought" : "text", text };
    }
    case "image": {
      const data = asString(block.data);
      const mimeType = asString(block.mimeType);
      return data !== null && mimeType !== null ? { type: "image", data, mimeType } : null;
    }
    case "resource_link": {
      const uri = asString(block.uri);
      return uri === null ? null : { type: "resource_link", uri, name: asString(block.name) ?? uri };
    }
    case "resource": {
      const resource = asRecord(block.resource);
      const text = resource ? asString(resource.text) : null;
      return text === null ? null : { type: thought ? "thought" : "text", text };
    }
    default:
      return null;
  }
}

function toolContents(raw: unknown[]): ToolContent[] {
  const out: ToolContent[] = [];
  for (const item of raw) {
    const entry = asRecord(item);
    if (!entry) {
      continue;
    }
    switch (entry.type) {
      case "content": {
        const block = asRecord(entry.content);
        if (!block) {
          break;
        }
        if (block.type === "text") {
          const text = asString(block.text);
          if (text !== null) {
            out.push({ type: "text", text });
          }
        } else if (block.type === "image") {
          const data = asString(block.data);
          const mimeType = asString(block.mimeType);
          if (data !== null && mimeType !== null) {
            out.push({ type: "image", data, mimeType });
          }
        } else if (block.type === "resource_link") {
          const uri = asString(block.uri);
          if (uri !== null) {
            out.push({
              type: "resource_link",
              uri,
              name: asString(block.name) ?? uri,
              mimeType: asString(block.mimeType),
            });
          }
        } else if (block.type === "resource") {
          const resource = asRecord(block.resource);
          const text = resource ? asString(resource.text) : null;
          if (text !== null) {
            out.push({ type: "text", text });
          }
        }
        break;
      }
      case "diff": {
        const path = asString(entry.path);
        const newText = asString(entry.newText);
        if (path !== null && newText !== null) {
          out.push({ type: "diff", path, oldText: asString(entry.oldText), newText });
        }
        break;
      }
      case "terminal": {
        const terminalId = asString(entry.terminalId);
        if (terminalId !== null) {
          out.push({ type: "terminal", terminalId });
        }
        break;
      }
    }
  }
  return out;
}

function toolLocations(raw: unknown[]): ToolLocation[] {
  const out: ToolLocation[] = [];
  for (const item of raw) {
    const entry = asRecord(item);
    const path = entry ? asString(entry.path) : null;
    if (entry && path !== null) {
      out.push({ path, line: asNumber(entry.line) });
    }
  }
  return out;
}

function toolKind(raw: unknown): ToolKind | null {
  const parsed = ToolKindSchema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}

function toolStatus(raw: unknown): ToolCallStatus | null {
  const parsed = ToolCallStatusSchema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}

function planEntries(raw: unknown): PlanEntry[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: PlanEntry[] = [];
  for (const item of raw) {
    const entry = asRecord(item);
    const content = entry ? asString(entry.content) : null;
    if (!entry || content === null) {
      continue;
    }
    const priority = entry.priority;
    const status = entry.status;
    out.push({
      content,
      priority: priority === "high" || priority === "low" ? priority : "medium",
      status: status === "in_progress" || status === "completed" ? status : "pending",
    });
  }
  return out;
}

function availableCommands(raw: unknown): AvailableCommand[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: AvailableCommand[] = [];
  for (const item of raw) {
    const entry = asRecord(item);
    const name = entry ? asString(entry.name) : null;
    if (!entry || name === null) {
      continue;
    }
    const input = asRecord(entry.input);
    out.push({
      name,
      description: asString(entry.description) ?? "",
      hint: input ? asString(input.hint) : null,
    });
  }
  return out;
}

/** Normalise the wire form of modes; exported for `session/new` responses. */
export function sessionModes(raw: unknown): SessionMode[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: SessionMode[] = [];
  for (const item of raw) {
    const entry = asRecord(item);
    const id = entry ? asString(entry.id) : null;
    if (!entry || id === null) {
      continue;
    }
    out.push({ id, name: asString(entry.name) ?? id, description: asString(entry.description) });
  }
  return out;
}

/** Normalise the wire form of config options; grouped selects are flattened. */
export function configOptions(raw: unknown): ConfigOption[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: ConfigOption[] = [];
  for (const item of raw) {
    const entry = asRecord(item);
    const id = entry ? asString(entry.id) : null;
    if (!entry || id === null) {
      continue;
    }
    const base = {
      id,
      name: asString(entry.name) ?? id,
      description: asString(entry.description),
      category: asString(entry.category),
    };
    if (entry.type === "boolean") {
      out.push({ ...base, type: "boolean", currentValue: entry.currentValue === true });
      continue;
    }
    if (entry.type !== "select") {
      continue;
    }
    const options: Extract<ConfigOption, { type: "select" }>["options"] = [];
    for (const optionRaw of Array.isArray(entry.options) ? entry.options : []) {
      const option = asRecord(optionRaw);
      if (!option) {
        continue;
      }
      if (Array.isArray(option.options)) {
        const group = asString(option.name) ?? asString(option.group);
        for (const grouped of option.options) {
          const inner = asRecord(grouped);
          const value = inner ? asString(inner.value) : null;
          if (inner && value !== null) {
            options.push({
              value,
              name: asString(inner.name) ?? value,
              description: asString(inner.description),
              group,
            });
          }
        }
      } else {
        const value = asString(option.value);
        if (value !== null) {
          options.push({
            value,
            name: asString(option.name) ?? value,
            description: asString(option.description),
            group: null,
          });
        }
      }
    }
    out.push({
      ...base,
      type: "select",
      currentValue: asString(entry.currentValue) ?? "",
      options,
    });
  }
  return out;
}

/** Normalise permission options, lifting the adapters' `_meta.permission.description`. */
export function permissionOptions(raw: unknown): PermissionOption[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  const out: PermissionOption[] = [];
  for (const item of raw) {
    const entry = asRecord(item);
    const optionId = entry ? asString(entry.optionId) : null;
    if (!entry || optionId === null) {
      continue;
    }
    const kind = entry.kind;
    const meta = asRecord(entry._meta);
    const permission = meta ? asRecord(meta.permission) : null;
    out.push({
      optionId,
      name: asString(entry.name) ?? optionId,
      kind:
        kind === "allow_once" || kind === "allow_always" || kind === "reject_always"
          ? kind
          : "reject_once",
      description: permission ? asString(permission.description) : null,
    });
  }
  return out;
}

/** Build the pending-permission record from a raw `session/request_permission`. */
export function pendingPermissionFromRequest(
  requestId: string,
  raw: unknown,
): PendingPermission | null {
  const request = asRecord(raw);
  const toolCall = request ? asRecord(request.toolCall) : null;
  const acpSessionId = request ? asString(request.sessionId) : null;
  const toolCallId = toolCall ? asString(toolCall.toolCallId) : null;
  if (!request || !toolCall || acpSessionId === null || toolCallId === null) {
    return null;
  }
  const meta = asRecord(request._meta);
  const permission = meta ? asRecord(meta.permission) : null;
  return {
    requestId,
    acpSessionId,
    toolCallId,
    title: (permission ? asString(permission.title) : null) ?? asString(toolCall.title),
    description: permission ? asString(permission.description) : null,
    kind: toolKind(toolCall.kind),
    input: toolCall.rawInput,
    options: permissionOptions(request.options),
  };
}

function toSubagentState(raw: unknown): SubagentState {
  switch (raw) {
    case "completed":
    case "failed":
    case "cancelled":
    case "disconnected":
    case "running":
      return raw;
    case "success":
    case "done":
      return "completed";
    case "error":
      return "failed";
    default:
      return "running";
  }
}

/* -------------------------------------------------------------------------- */
/* Loose readers                                                               */
/* -------------------------------------------------------------------------- */

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/* -------------------------------------------------------------------------- */
/* Derived views                                                               */
/* -------------------------------------------------------------------------- */

/** Every tool call in the transcript, in order, nested ones included. */
export function allToolCalls(state: SessionState): ToolCallPart[] {
  const out: ToolCallPart[] = [];
  const walk = (parts: Part[]) => {
    for (const part of parts) {
      if (part.type === "tool_call") {
        out.push(part);
        walk(part.children);
      } else if (part.type === "subagent") {
        walk(part.parts);
      }
    }
  };
  for (const turn of state.turns) {
    walk(turn.parts);
  }
  return out;
}

/** The trailing agent text of the last turn — what a harness prints as the reply. */
export function lastAgentText(state: SessionState): string {
  const turn = state.turns.findLast((candidate) => candidate.role === "agent");
  if (!turn) {
    return "";
  }
  return turn.parts
    .filter((part): part is Extract<Part, { type: "text" }> => part.type === "text")
    .map((part) => part.text)
    .join("");
}
