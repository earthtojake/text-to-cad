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
 *     always update the state; a mode change also becomes a part when a
 *     turn is open (the adapters send most of these right after
 *     `session/new`). The commands list never does: it is the composer's,
 *     `SessionState.availableCommands`. The `available_commands` part a turn
 *     used to carry is still in `PartSchema` (a turn's `parts`), only so
 *     snapshots written before the change parse; nothing produces it.
 *     Only the root session's count: a subagent's plan lands in its own
 *     part, the rest of what it reports about itself is dropped.
 *   - An update under a session id that is neither the root nor a known
 *     subagent is parked (bounded) until that subagent's spawn arrives,
 *     rather than glued onto the root's reply. `parked` is not in the
 *     schema, so no wire copy carries it: a renderer that takes a
 *     `session.state` while a child has updates parked lacks them, and when
 *     main later unparks them into the subagent's part the renderer's copy
 *     of that part is short. Accepted: it needs a spawn to trail its first
 *     updates across a `session.state` (sent on connect and load only), the
 *     loss is those early updates' rows, and the next `session.state` heals
 *     it. Carrying raw parked diffs on every snapshot is the worse trade.
 *   - A tool call id is looked up across every turn: a late update (after a
 *     cancel, a background command) updates the row where it is, and an
 *     update for an unknown id never opens a turn when none is open.
 *   - Content after its turn ended (a chunk or a call behind `prompt/end`)
 *     rides on the last agent turn, or a closed one of its own; it never
 *     opens a turn nothing would end. A replay, which has no `prompt/start`,
 *     still opens its own. Late text is a part of its own, never glued onto
 *     the answer the turn ended with; the chunks behind its first join it.
 *   - A cancelled or failed turn settles what was still pending or running
 *     in it; an ordinary end does not (a background command can outlive it).
 *   - `status: closed` and `status: error` end the open turn and settle it: a
 *     closed connection stops it (`cancelled`, calls and subagents
 *     `cancelled`), an errored one ends it with no stop reason (calls and
 *     subagents `failed`). The adapter is gone and will send neither
 *     `prompt/end` nor `prompt/error`, and `retire` files that closed state
 *     as the stored snapshot. A call that is settled, or completed, is never
 *     revived by a later `pending` or `in_progress` for it.
 *   - Every turn end cancels the permission cards still pending, in any turn:
 *     `prompt/end` whatever its stop reason, `prompt/error`, and the two
 *     statuses above. Main cancels the client's pending permissions before it
 *     dispatches `prompt/end`, so the cards and the requests agree.
 *   - `prompt/error` on a last turn that has already ended (a crash reports
 *     `status: error` first) adds the error part to that turn rather than
 *     opening a new one.
 *   - `lateChunk` marks that the first chunk behind `prompt/end` has opened a
 *     part, so the chunks after it join that part. `prompt/start` clears it;
 *     it is not in the schema, so neither a stored snapshot (`withoutParked`,
 *     which `retire`'s closed state goes through) nor a `session.state` from a
 *     load carries it, and a loaded session starts without it.
 */
import {
  type AvailableCommand,
  type ConfigOption,
  type ContextBreakdownEntry,
  type Part,
  type PendingPermission,
  type PermissionOption,
  type PlanEntry,
  type PromptBlock,
  type RateLimit,
  type RawSessionUpdate,
  type SessionEvent,
  type SessionMode,
  type SessionState,
  type SubagentState,
  type TokenTotals,
  type ToolCallPart,
  type ToolCallStatus,
  type ToolContent,
  type ToolKind,
  type ToolLocation,
  type Turn,
  type TurnUsage,
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
        title: event.title ?? state.title,
      };

    case "session/loaded":
      return { ...closeOpenTurn(state, event.at, replayedEnd(state)), status: "idle" };

    case "prompt/start": {
      const { lateChunk: _late, ...settled } = state;
      const closed = closeOpenTurn(settled, event.at, null);
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
      const next = closeOpenTurn(
        state,
        event.at,
        event.stopReason,
        event.stopReason === "cancelled" ? { tool: "cancelled", subagent: "cancelled" } : undefined,
      );
      return {
        ...next,
        // A turn that ends takes its unanswered permission requests with it, whatever the stop
        // reason: main resolves them on a cancel, but an `end_turn` or a `refusal` with a request
        // still open sends no resolve, and the card would stay clickable (and the transcript
        // pulled down to it) with nobody to take the answer.
        turns: cancelPendingCards(next.turns),
        status: "idle",
        lastTurnUsage: event.usage ?? next.lastTurnUsage,
        sessionUsage: event.usage ? addTurnUsage(next.sessionUsage, event.usage) : next.sessionUsage,
        pendingPermissions: [],
      };
    }

    case "prompt/error": {
      const addError = (parts: Part[]) => [...parts, { type: "error", message: event.message } as Part];
      // A turn already ended (a crash reports `status: error` before the SDK's rejection arrives,
      // and that ends it) keeps its error: a new turn for it would leave the real one without.
      const last = state.turns.at(-1);
      const withError =
        last && last.endedAt !== null
          ? withClosedParts(state, event.at, addError)
          : withRootParts(state, event.at, addError);
      const closed = closeOpenTurn(withError, event.at, null, { tool: "failed", subagent: "failed" });
      return {
        ...closed,
        turns: cancelPendingCards(closed.turns),
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
      // Not `create`: a request that arrives with no turn open (the prompt has
      // ended, or was cancelled, and the adapter asked late) must not open one
      // — nothing would ever end it, and the resolve below would call the
      // session running. It rides on the last turn, or on a closed one.
      const add = (parts: Part[]) => [...parts, part];
      const next = withSessionParts(state, request.acpSessionId, event.at, add, false);
      if (next === state) {
        return {
          ...withClosedParts(state, event.at, add),
          status: "waiting",
          pendingPermissions: [...state.pendingPermissions, request],
        };
      }
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
      // A turn without the request keeps its identity, so answering one does not re-render every
      // turn of a long transcript (`mapPartsDeep` returns the same array where nothing changed).
      const turns = state.turns.map((turn) => {
        const parts = mapPartsDeep(turn.parts, (part) =>
          part.type === "permission_request" && part.requestId === event.requestId
            ? { ...part, outcome: event.outcome }
            : part,
        );
        return parts === turn.parts ? turn : { ...turn, parts };
      });
      return {
        ...state,
        turns,
        pendingPermissions,
        status:
          state.status === "waiting" && pendingPermissions.length === 0
            ? hasOpenAgentTurn(state)
              ? "running"
              : "idle"
            : state.status,
      };
    }

    case "config/updated":
      return { ...state, configOptions: event.configOptions };

    case "status":
      if (event.status === "closed" || event.status === "error") {
        // The adapter is gone, and with it whoever would take an answer or end a turn: `retire`
        // drops the connection's own resolve before it can be dispatched, and a Disconnect
        // mid-turn gets neither a `prompt/end` (the adapter is dead) nor a `prompt/error`
        // (`prompt()` skips it while `closing`). So the open turn ends here, its unfinished work
        // settled, and a card left pending would stay answerable.
        const closed = closeOpenTurn(
          state,
          event.at,
          event.status === "closed" && hasOpenAgentTurn(state) ? "cancelled" : null,
          event.status === "closed"
            ? { tool: "cancelled", subagent: "cancelled" }
            : { tool: "failed", subagent: "failed" },
        );
        return {
          ...closed,
          turns: cancelPendingCards(closed.turns),
          pendingPermissions: [],
          status: event.status,
          error: event.error,
        };
      }
      return { ...state, status: event.status, error: event.error };
  }
}

/* -------------------------------------------------------------------------- */
/* session/update                                                               */
/* -------------------------------------------------------------------------- */

/** Updates about the session itself: a subagent's are dropped. */
const ROOT_ONLY: ReadonlySet<string> = new Set([
  "plan_removed",
  "available_commands_update",
  "current_mode_update",
  "config_option_update",
  "session_info_update",
  "usage_update",
]);

function applyUpdate(
  state: SessionState,
  acpSessionId: string,
  update: RawSessionUpdate,
  at: number,
): SessionState {
  const u = update as Record<string, unknown>;
  // Before `session/connected` names the root, every update is the root's.
  const isRoot = state.acpSessionId === null || acpSessionId === state.acpSessionId;
  if (!isRoot && !state.subagentSessionIds.includes(acpSessionId)) {
    return park(state, acpSessionId, update, at);
  }
  if (!isRoot && ROOT_ONLY.has(update.sessionUpdate)) {
    return state;
  }
  switch (update.sessionUpdate) {
    case "user_message_chunk": {
      const part = contentBlockToPart(u.content, false, true);
      return part ? appendUserChunk(state, at, part, asString(u.messageId)) : state;
    }

    case "agent_message_chunk":
    case "agent_thought_chunk": {
      const part = contentBlockToPart(u.content, update.sessionUpdate === "agent_thought_chunk");
      if (!part) {
        return state;
      }
      // Behind `prompt/end` the first chunk is a part of its own, not the tail of the answer the
      // turn ended with ("First answer.Background task finished."); the chunks that follow it join.
      const join = state.lateChunk === true;
      return withUpdateOrLate(
        state,
        acpSessionId,
        u,
        at,
        (parts) => appendChunk(parts, part),
        (parts) => (join ? appendChunk(parts, part) : [...parts, part]),
      );
    }

    case "tool_call":
    case "tool_call_update": {
      const id = asString(u.toolCallId);
      if (!id) {
        return state;
      }
      const turnOpen = state.turns.at(-1)?.endedAt === null;
      // While a turn is open an announcement is a new row in it, even if an
      // earlier turn used the same id (the fake agent does). An update — or
      // an announcement with no turn open (a background call re-announced
      // after its turn ended) — is news about a call that already has a row
      // somewhere in its own session.
      if (update.sessionUpdate === "tool_call_update" || !turnOpen) {
        const inPlace = updateToolCallInSession(state, acpSessionId, id, u);
        if (inPlace) {
          return inPlace;
        }
        if (!turnOpen && update.sessionUpdate === "tool_call_update") {
          // A late update for a call nobody announced, with no turn open:
          // opening one would put a blank row in a turn nobody started.
          return state;
        }
      }
      return withUpdateOrLate(state, acpSessionId, u, at, (parts) => upsertToolCall(parts, id, u));
    }

    case "plan":
      return applyPlan(state, acpSessionId, at, isRoot, planEntries(u.entries));

    case "plan_update": {
      const plan = asRecord(u.plan);
      if (plan?.type !== "items") {
        return state;
      }
      return applyPlan(state, acpSessionId, at, isRoot, planEntries(plan.entries));
    }

    case "plan_removed":
      return { ...state, plan: null };

    case "available_commands_update":
      // The session's, never a turn's: the Claude adapter sends the whole
      // list (129 commands) mid-turn as well as after session/new, and a
      // copy in the open turn rode in every turn's parts and snapshot — and
      // was gone after a session/load, whose replay sends none.
      return { ...state, availableCommands: availableCommands(u.availableCommands) };

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
      // A `usage_update` carries two independent things: the window, and —
      // when the Claude adapter is forwarding a `rate_limit_event` — one of
      // the account's plan limits. Either can be there without the other, so
      // the limit is folded first and a window that did not parse does not
      // throw the limit away with it.
      const limit = rateLimit(u._meta);
      const withLimit = limit
        ? { ...state, rateLimits: { ...state.rateLimits, [limit.type]: limit } }
        : state;
      const used = asNumber(u.used);
      const size = asNumber(u.size);
      if (used === null || size === null) {
        return withLimit;
      }
      const cost = asRecord(u.cost);
      const amount = cost ? asNumber(cost.amount) : null;
      const currency = cost ? asString(cost.currency) : null;
      return {
        ...withLimit,
        contextUsage: {
          used,
          size,
          cost: amount !== null && currency !== null ? { amount, currency } : null,
          breakdown: contextBreakdown(u._meta),
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
      // Not `create`: a spawn behind `prompt/end` must not open a turn nothing would end.
      const next = withUpdateOrLate(state, acpSessionId, u, at, (parts) =>
        findSubagent(parts, childId) ? parts : [...parts, part],
      );
      return unpark(
        {
          ...next,
          subagentSessionIds: next.subagentSessionIds.includes(childId)
            ? next.subagentSessionIds
            : [...next.subagentSessionIds, childId],
        },
        childId,
      );
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

/** A plan: the root's is the session's and, in an open turn, a part too; a subagent's only a part. */
function applyPlan(
  state: SessionState,
  acpSessionId: string,
  at: number,
  isRoot: boolean,
  entries: PlanEntry[],
): SessionState {
  if (!isRoot) {
    return withSessionParts(state, acpSessionId, at, (parts) => setPlan(parts, entries), false);
  }
  const next = { ...state, plan: entries };
  return hasOpenAgentTurn(next)
    ? withSessionParts(next, acpSessionId, at, (parts) => setPlan(parts, entries), false)
    : next;
}

/* -------------------------------------------------------------------------- */
/* Turn plumbing                                                               */
/* -------------------------------------------------------------------------- */

function hasOpenAgentTurn(state: SessionState): boolean {
  const last = state.turns.at(-1);
  return last?.role === "agent" && last.endedAt === null;
}

/**
 * The stop reason of a turn a `session/load` replay closes. The replay says
 * nothing about how a turn ended — no `session/prompt` answer comes with it —
 * only that it did, being history; `end_turn` is that, where null would read
 * as a turn still open and leave a replayed turn unlike the live one it was.
 * A user turn never has a stop reason, live or replayed.
 */
function replayedEnd(state: SessionState): Turn["stopReason"] {
  return state.turns.at(-1)?.role === "agent" ? "end_turn" : null;
}

/** What a turn that was cancelled or failed leaves its unfinished work as. */
type Settle = { tool: ToolCallStatus; subagent: SubagentState };

function closeOpenTurn(
  state: SessionState,
  at: number,
  stopReason: Turn["stopReason"],
  settle?: Settle,
) {
  const last = state.turns.at(-1);
  if (!last || last.endedAt !== null) {
    return state;
  }
  const parts = settle ? settleParts(last.parts, settle) : last.parts;
  const closed: Turn = { ...last, parts, endedAt: at, stopReason };
  return { ...state, turns: [...state.turns.slice(0, -1), closed] };
}

/** Every pending or running call, and every running subagent, in `parts` — however deep. */
function settleParts(parts: Part[], settle: Settle): Part[] {
  return mapPartsDeep(parts, (part) => {
    if (part.type === "tool_call" && (part.status === "pending" || part.status === "in_progress")) {
      return { ...part, status: settle.tool };
    }
    if (part.type === "subagent" && part.state === "running") {
      return { ...part, state: settle.subagent };
    }
    return part;
  });
}

/** Every permission card still pending, in any turn, marked cancelled; the same array back where none was. */
function cancelPendingCards(turns: Turn[]): Turn[] {
  const next = turns.map((turn) => {
    const parts = mapPartsDeep(turn.parts, (part) =>
      part.type === "permission_request" && part.outcome.state === "pending"
        ? { ...part, outcome: { state: "cancelled" } }
        : part,
    );
    return parts === turn.parts ? turn : { ...turn, parts };
  });
  return next.every((turn, index) => turn === turns[index]) ? turns : next;
}

/** How many updates, and how many bytes of them, are held for not-yet-spawned subagents; the oldest go first. */
const PARKED_LIMIT = 200;
/** In UTF-8 bytes, what the entries weigh on the wire. */
const PARKED_BYTES = 256 * 1024;
const UTF8 = new TextEncoder();

function park(state: SessionState, acpSessionId: string, update: RawSessionUpdate, at: number): SessionState {
  const bytes = UTF8.encode(JSON.stringify(update)).length;
  const parked = [...(state.parked ?? []), { acpSessionId, update, at, bytes }];
  let total = parked.reduce((sum, entry) => sum + entry.bytes, 0);
  let drop = 0;
  // The newest always stays: a spawn is usually right behind its first
  // update, and dropping that update on arrival would lose it for nothing.
  while (drop < parked.length - 1 && (parked.length - drop > PARKED_LIMIT || total > PARKED_BYTES)) {
    total -= parked[drop]!.bytes;
    drop += 1;
  }
  if (drop === 0) {
    return { ...state, parked };
  }
  if (!state.parkedDropWarned) {
    // The one impurity here: a dropped update is data lost, and saying so
    // once per session is worth more than a silent cap.
    console.warn(
      `[acp] dropped ${drop} update(s) parked for a subagent that has not been spawned (cap ${PARKED_LIMIT} / ${PARKED_BYTES} bytes)`,
    );
  }
  const kept = parked.slice(drop);
  const { parked: _old, ...rest } = state;
  return kept.length > 0 ? { ...rest, parked: kept, parkedDropWarned: true } : { ...rest, parkedDropWarned: true };
}

/** The state without what the reducer holds for itself: what a snapshot should store. */
export function withoutParked(state: SessionState): SessionState {
  const { parked: _parked, parkedDropWarned: _warned, lateChunk: _late, ...rest } = state;
  return rest;
}

/** Fold what was parked for `childId`, in arrival order, now that it has somewhere to go. */
function unpark(state: SessionState, childId: string): SessionState {
  const all = state.parked ?? [];
  const mine = all.filter((entry) => entry.acpSessionId === childId);
  if (mine.length === 0) {
    return state;
  }
  const rest = all.filter((entry) => entry.acpSessionId !== childId);
  const { parked: _dropped, ...cleared } = state;
  let next: SessionState = rest.length > 0 ? { ...cleared, parked: rest } : cleared;
  for (const entry of mine) {
    next = applyUpdate(next, entry.acpSessionId, entry.update, entry.at);
  }
  return next;
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

/** Parts for a moment when no turn is open: the last agent turn takes them, or a closed one of their own. */
function withClosedParts(state: SessionState, at: number, fn: (parts: Part[]) => Part[]): SessionState {
  const last = state.turns.at(-1);
  if (last?.role === "agent") {
    return { ...state, turns: [...state.turns.slice(0, -1), { ...last, parts: fn(last.parts) }] };
  }
  const turn: Turn = {
    id: `t${state.turns.length + 1}`,
    role: "agent",
    parts: fn([]),
    startedAt: at,
    endedAt: at,
    stopReason: null,
  };
  return { ...state, turns: [...state.turns, turn] };
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
  create = true,
): SessionState {
  const parentId = claudeParentToolUseId(update);
  if (!parentId) {
    return withSessionParts(state, acpSessionId, at, fn, create);
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
  return found ? { ...state, turns } : withSessionParts(state, acpSessionId, at, fn, create);
}

/**
 * `withUpdateTarget`, except that content arriving after its turn ended (a chunk or a call the
 * adapter sent behind `prompt/end`) does not open a turn: nothing would ever end it, and the
 * last turn would keep its streaming cursor with the session idle. It rides on the last agent
 * turn, or on a closed one of its own. A replay (`connecting`) has no `prompt/start` and opens
 * its own turns, and a session that has had no turn yet opens one as before.
 */
function withUpdateOrLate(
  state: SessionState,
  acpSessionId: string,
  update: Record<string, unknown>,
  at: number,
  fn: (parts: Part[]) => Part[],
  late?: (parts: Part[]) => Part[],
): SessionState {
  const last = state.turns.at(-1);
  if (!last || last.endedAt === null || state.status === "connecting") {
    return withUpdateTarget(state, acpSessionId, update, at, fn);
  }
  const placed = withUpdateTarget(state, acpSessionId, update, at, fn, false);
  if (placed !== state) {
    return placed;
  }
  // `late` is how content that lands on a closed turn is added, where that differs from `fn`.
  const closed = withClosedParts(state, at, late ?? fn);
  return late ? { ...closed, lateChunk: true } : closed;
}

function claudeParentToolUseId(update: Record<string, unknown>): string | null {
  const meta = asRecord(update._meta);
  const claude = meta ? asRecord(meta.claudeCode) : null;
  return claude ? asString(claude.parentToolUseId) : null;
}

/**
 * A replayed user message. Chunks carrying the same ACP `messageId` are one
 * message and concatenate; a different id is the next message and starts its
 * own turn. Without ids there is no telling one streamed block from the next
 * prompt, so each chunk stays its own part (the bubble joins them with a
 * line break) rather than running two prompts together.
 */
function appendUserChunk(
  state: SessionState,
  at: number,
  part: Part,
  messageId: string | null,
): SessionState {
  const last = state.turns.at(-1);
  const sameMessage =
    last?.role === "user" &&
    last.endedAt === null &&
    (messageId === null || last.messageId === undefined || last.messageId === messageId);
  if (last && sameMessage) {
    const parts = messageId !== null && last.messageId === messageId ? appendChunk(last.parts, part) : [...last.parts, part];
    const updated: Turn = { ...last, parts };
    return { ...state, turns: [...state.turns.slice(0, -1), updated] };
  }
  const closed = closeOpenTurn(state, at, replayedEnd(state));
  const turn: Turn = {
    id: `t${closed.turns.length + 1}`,
    role: "user",
    parts: [part],
    startedAt: at,
    endedAt: null,
    stopReason: null,
    ...(messageId !== null ? { messageId } : {}),
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

/**
 * Merge `update` into the call with this id in the session that sent it —
 * the root's parts (Claude's flattened children included), or that
 * subagent's — taking the newest turn that has one, since an id can come
 * back in a later turn. Another session's call with the same id is never
 * touched. Null when the session has no such call.
 */
function updateToolCallInSession(
  state: SessionState,
  acpSessionId: string,
  id: string,
  update: Record<string, unknown>,
): SessionState | null {
  const isRoot = state.acpSessionId === null || acpSessionId === state.acpSessionId;
  for (let index = state.turns.length - 1; index >= 0; index -= 1) {
    const turn = state.turns[index]!;
    let parts: Part[] | null;
    if (isRoot) {
      parts = mergeInScope(turn.parts, id, update);
    } else {
      let merged: Part[] | null = null;
      const mapped = mapPartsDeep(turn.parts, (part) => {
        if (merged === null && part.type === "subagent" && part.sessionId === acpSessionId) {
          merged = mergeInScope(part.parts, id, update);
          return merged ? { ...part, parts: merged } : part;
        }
        return part;
      });
      parts = merged ? mapped : null;
    }
    if (parts) {
      const updated = { ...turn, parts };
      return { ...state, turns: state.turns.map((candidate, i) => (i === index ? updated : candidate)) };
    }
  }
  return null;
}

/** The first call with this id in `parts` and its tool calls' children — never inside a subagent, which is another session. */
function mergeInScope(parts: Part[], id: string, update: Record<string, unknown>): Part[] | null {
  for (let i = 0; i < parts.length; i += 1) {
    const part = parts[i]!;
    if (part.type !== "tool_call") {
      continue;
    }
    const next =
      part.id === id
        ? mergeToolCall(part, update)
        : (() => {
            const children = mergeInScope(part.children, id, update);
            return children ? { ...part, children } : null;
          })();
    if (next) {
      return parts.map((candidate, j) => (j === i ? next : candidate));
    }
  }
  return null;
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
  const joined = delta === null ? part.stream : part.stream + delta;
  const truncated = joined.length > STREAM_TAIL;
  // A call its turn settled (cancelled or failed), or that finished, stays so unless the agent
  // says how it ended: a late `in_progress` must not bring it back to life.
  const settled =
    (part.status === "cancelled" || part.status === "failed" || part.status === "completed") &&
    (status === "pending" || status === "in_progress");
  return {
    ...part,
    kind: kind ?? part.kind,
    status: settled ? part.status : (status ?? part.status),
    title: title ?? part.title ?? name ?? part.name ?? "",
    name: name ?? part.name,
    input: update.rawInput !== undefined ? update.rawInput : part.input,
    output: update.rawOutput !== undefined ? update.rawOutput : part.output,
    content: content ?? part.content,
    locations: locations ?? part.locations,
    stream: truncated ? joined.slice(-STREAM_TAIL) : joined,
    ...(truncated ? { streamTruncated: true } : {}),
  };
}

/** How much of a call's streamed output is kept: the tail, like the terminal's. */
const STREAM_TAIL = 64 * 1024;

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
      return { type: "resource", uri: block.uri, name: nameOfUri(block.uri), text: block.text, mimeType: block.mimeType };
  }
}

/** `attachment:///notes%20v2.md` → `notes v2.md`. */
function nameOfUri(uri: string): string {
  const last = uri.split(/[\\/]/).pop() || uri;
  try {
    return decodeURIComponent(last);
  } catch {
    return last;
  }
}

/** `user`: an embedded resource is the person's attachment, kept whole; an agent's reads as text. */
function contentBlockToPart(raw: unknown, thought = false, user = false): Part | null {
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
      if (text === null) {
        return null;
      }
      const uri = resource ? asString(resource.uri) : null;
      if (user && uri !== null) {
        return { type: "resource", uri, name: nameOfUri(uri), text, mimeType: asString(resource?.mimeType) };
      }
      return { type: thought ? "thought" : "text", text };
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
/** `_meta.kind`, which is where both adapters say what a mode or preset *is*. */
function metaKind(entry: Record<string, unknown>): string | null {
  const meta = asRecord(entry._meta);
  return meta ? asString(meta.kind) : null;
}

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
    out.push({
      id,
      name: asString(entry.name) ?? id,
      description: asString(entry.description),
      kind: metaKind(entry),
    });
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
              kind: metaKind(inner),
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
            kind: metaKind(option),
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
/* Token accounting                                                            */
/* -------------------------------------------------------------------------- */

/** Add one turn's `usage` to the session's running totals. */
function addTurnUsage(totals: TokenTotals | null, usage: TurnUsage): TokenTotals {
  const base = totals ?? {
    turns: 0,
    totalTokens: 0,
    inputTokens: 0,
    outputTokens: 0,
    cachedReadTokens: 0,
    cachedWriteTokens: 0,
  };
  return {
    turns: base.turns + 1,
    totalTokens: base.totalTokens + usage.totalTokens,
    inputTokens: base.inputTokens + usage.inputTokens,
    outputTokens: base.outputTokens + usage.outputTokens,
    cachedReadTokens: base.cachedReadTokens + (usage.cachedReadTokens ?? 0),
    cachedWriteTokens: base.cachedWriteTokens + (usage.cachedWriteTokens ?? 0),
  };
}

/**
 * The category breakdown of a `usage_update`, out of its `_meta`.
 *
 * ACP has no field for one and neither adapter sends one today, so this
 * reads an extension: any `_meta` key whose name ends in `breakdown` — bare,
 * `contextBreakdown`, or namespaced the way the Claude adapter namespaces its
 * own (`_claude/contextBreakdown`) — holding either a list of
 * `{ id, name, tokens }` or a plain `name: tokens` map. Anything else, and
 * anything that adds up to nothing, reads as no breakdown at all: the popover
 * then shows the window and the token counts and says nothing about
 * categories, which is the honest answer when the agent did not say.
 */
function contextBreakdown(meta: unknown): ContextBreakdownEntry[] | null {
  const record = asRecord(meta);
  if (!record) {
    return null;
  }
  const key = Object.keys(record).find((candidate) => candidate.toLowerCase().endsWith("breakdown"));
  if (key === undefined) {
    return null;
  }
  const raw = record[key];
  const entries: ContextBreakdownEntry[] = [];
  if (Array.isArray(raw)) {
    for (const item of raw) {
      const fields = asRecord(item);
      if (!fields) {
        continue;
      }
      const tokens = asNumber(fields.tokens) ?? asNumber(fields.used) ?? asNumber(fields.value);
      const name = asString(fields.name) ?? asString(fields.label) ?? asString(fields.title);
      const id = asString(fields.id) ?? name;
      if (tokens === null || tokens <= 0 || id === null) {
        continue;
      }
      entries.push({ id, name: name ?? id, tokens });
    }
  } else {
    const fields = asRecord(raw);
    if (!fields) {
      return null;
    }
    for (const [id, value] of Object.entries(fields)) {
      const tokens = asNumber(value);
      if (tokens === null || tokens <= 0) {
        continue;
      }
      entries.push({ id, name: id, tokens });
    }
  }
  return entries.length > 0 ? entries : null;
}

/**
 * One plan limit out of a `usage_update`'s `_meta`.
 *
 * The Claude adapter forwards the SDK's `rate_limit_event` verbatim under
 * `_claude/rateLimit`; the key is matched loosely (any `_meta` key ending in
 * `ratelimit`) for the same reason the breakdown is, and every field is read
 * defensively — an event this build does not understand is ignored, never
 * thrown on. Two units are normalised here so nothing downstream has to
 * guess:
 *
 *   - `utilization` becomes a fraction of the limit. The SDK sends 0…1; a
 *     value above 1 is read as a percentage, because the only other thing a
 *     number like `63` can mean is 63%.
 *   - `resetsAt` becomes epoch **milliseconds**. The SDK sends epoch
 *     seconds, so anything past the year 2001 in milliseconds (`> 1e12`) is
 *     already milliseconds and is left alone.
 *
 * A limit with no `rateLimitType` is dropped: `rateLimits` is keyed by type,
 * and an unnamed limit has nowhere to go and nothing to be labelled with.
 */
function rateLimit(meta: unknown): RateLimit | null {
  const record = asRecord(meta);
  if (!record) {
    return null;
  }
  const key = Object.keys(record).find((candidate) => candidate.toLowerCase().endsWith("ratelimit"));
  if (key === undefined) {
    return null;
  }
  const fields = asRecord(record[key]);
  if (!fields) {
    return null;
  }
  const type = asString(fields.rateLimitType);
  const raw = asNumber(fields.utilization);
  if (type === null || type === "" || raw === null) {
    return null;
  }
  const fraction = raw > 1 ? raw / 100 : raw;
  const resets = asNumber(fields.resetsAt);
  const status = asString(fields.status);
  return {
    type,
    status: status === "allowed_warning" || status === "rejected" ? status : "allowed",
    utilization: Math.max(0, Math.min(1, fraction)),
    resetsAt: resets === null || resets <= 0 ? null : resets > 1e12 ? resets : resets * 1000,
    isUsingOverage: typeof fields.isUsingOverage === "boolean" ? fields.isUsingOverage : null,
  };
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
