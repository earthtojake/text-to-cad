/**
 * The transcript, on this machine, so a session paints before its agent has
 * said a word.
 *
 * The agent owns the transcript (`sessions.ts`): a session that is not
 * connected has nothing to draw, and `session/load` — the only way to get it
 * back — costs a spawn, an `initialize` and a replay (README, "Opening a
 * session"). So every reduced `SessionState` main sees is written here,
 * debounced, and the renderer paints *that* the moment a row is clicked
 * while the real load runs behind it.
 *
 * It is a cache and it is treated as one: a row that no longer parses is
 * dropped and the session falls back to the spinner, exactly as a session
 * created before this feature does. Nothing is ever read back into a live
 * connection — the live state is the agent's, and this is a picture of it.
 *
 * Two caps, because a transcript is not a bounded thing:
 *
 *   - `SNAPSHOT_TOOL_TEXT_CAP` per tool call, on the four fields that carry
 *     bulk (`stream`, each `content` text, `input`, `output`). A `Read` of a
 *     10k-line file is 400 KB of one row nobody scrolls back to.
 *   - `SNAPSHOT_JSON_CAP` on the whole snapshot, applied by dropping the
 *     oldest turns until it fits (the newest turn always stays). This is
 *     what bounds a session with two thousand small turns in it, and what
 *     bounds pasted images.
 *
 * Both apply to the snapshot only. The live state main holds and the state
 * the renderer folds events into are untouched: a truncated tool output is a
 * thing you see for the second or two before the real state lands, never a
 * thing the agent is told.
 */
import { SessionStateSchema, type Part, type SessionState } from "../../shared/acp/types";

/** Characters kept per bulk field of a tool call, in the snapshot. */
export const SNAPSHOT_TOOL_TEXT_CAP = 4_096;

/** Characters of JSON one session's snapshot may occupy. */
export const SNAPSHOT_JSON_CAP = 512 * 1_024;

/**
 * How long a session's state has to stop changing before it is written. A
 * streaming turn is thousands of reducer events a minute and every one of
 * them is a whole new state; a write per event would be a write per token.
 */
export const SNAPSHOT_DEBOUNCE_MS = 750;

/** Where snapshots live. Sqlite in the app (`session_state`, migration 10). */
export interface SnapshotStore {
  read(sessionId: string): unknown | null;
  write(sessionId: string, json: string): void;
  remove(sessionId: string): void;
}

export type SnapshotWriterDeps = {
  store: SnapshotStore;
  debounceMs?: number;
  /** Injected in the tests; `setTimeout` in the app. */
  schedule?: (run: () => void, ms: number) => { cancel: () => void };
};

const timerSchedule = (run: () => void, ms: number) => {
  const handle = setTimeout(run, ms);
  handle.unref?.();
  return { cancel: () => clearTimeout(handle) };
};

/** `… (12 KB dropped)` — a truncation you can see, rather than text that stops. */
function capText(text: string, cap = SNAPSHOT_TOOL_TEXT_CAP): string {
  if (text.length <= cap) {
    return text;
  }
  const dropped = Math.round((text.length - cap) / 1024);
  return `${text.slice(0, cap)}\n… (${dropped} KB dropped from this snapshot)`;
}

/** An `unknown` tool payload, dropped rather than truncated: half a JSON blob is not JSON. */
function capUnknown(value: unknown): unknown {
  if (value === null || value === undefined || typeof value !== "object") {
    return value;
  }
  try {
    return JSON.stringify(value).length > SNAPSHOT_TOOL_TEXT_CAP ? null : value;
  } catch {
    return null;
  }
}

function capPart(part: Part): Part {
  switch (part.type) {
    case "tool_call":
      return {
        ...part,
        input: capUnknown(part.input),
        output: capUnknown(part.output),
        stream: capText(part.stream),
        content: part.content.map((item) => {
          if (item.type === "text") {
            return { ...item, text: capText(item.text) };
          }
          if (item.type === "diff") {
            return {
              ...item,
              oldText: item.oldText === null ? null : capText(item.oldText),
              newText: capText(item.newText),
            };
          }
          return item;
        }),
        children: part.children.map(capPart),
      };
    case "subagent":
      return { ...part, parts: part.parts.map(capPart) };
    default:
      return part;
  }
}

/**
 * The state as it is worth keeping: the bulk capped, and the three fields
 * that only mean something while a connection is up neutralised.
 *
 * `status` becomes `idle` and `error` null because a snapshot is only ever
 * painted when nothing is connected — a stored `closed` would grey the
 * composer of a session that is about to be live, and a stored `error` would
 * show a failure from last week beside a working thread.
 * `pendingPermissions` goes because a request cannot be answered without the
 * agent that asked it; the requests stay in the transcript as history.
 */
export function trimForSnapshot(state: SessionState): SessionState {
  const capped: SessionState = {
    ...state,
    status: "idle",
    error: null,
    pendingPermissions: [],
    turns: state.turns.map((turn) => ({ ...turn, parts: turn.parts.map(capPart) })),
  };
  return fitToBudget(capped);
}

/** Drop the oldest turns until the JSON fits. The newest turn is never dropped. */
function fitToBudget(state: SessionState): SessionState {
  let turns = state.turns;
  while (turns.length > 1 && JSON.stringify({ ...state, turns }).length > SNAPSHOT_JSON_CAP) {
    turns = turns.slice(1);
  }
  return turns === state.turns ? state : { ...state, turns };
}

/**
 * The debounced writer. One pending write per session, coalesced: a turn that
 * streams for a minute is one row written a second after it stops.
 */
export class SessionSnapshotWriter {
  private readonly pending = new Map<string, { state: SessionState; timer: { cancel: () => void } }>();
  private readonly debounceMs: number;
  private readonly schedule: NonNullable<SnapshotWriterDeps["schedule"]>;

  constructor(private readonly deps: SnapshotWriterDeps) {
    this.debounceMs = deps.debounceMs ?? SNAPSHOT_DEBOUNCE_MS;
    this.schedule = deps.schedule ?? timerSchedule;
  }

  /** Remember this state; write it once the session has been quiet. */
  save(sessionId: string, state: SessionState): void {
    this.pending.get(sessionId)?.timer.cancel();
    this.pending.set(sessionId, {
      state,
      timer: this.schedule(() => this.flush(sessionId), this.debounceMs),
    });
  }

  /** Write the pending state now, if there is one. Called on quit. */
  flush(sessionId: string): void {
    const entry = this.pending.get(sessionId);
    if (!entry) {
      return;
    }
    entry.timer.cancel();
    this.pending.delete(sessionId);
    try {
      this.deps.store.write(sessionId, JSON.stringify(trimForSnapshot(entry.state)));
    } catch (error) {
      // A snapshot is a nicety. A session must not fail to run because its
      // picture could not be filed.
      console.warn(`[acp] the snapshot of ${sessionId.slice(0, 8)} was not written: ${String(error)}`);
    }
  }

  flushAll(): void {
    for (const sessionId of [...this.pending.keys()]) {
      this.flush(sessionId);
    }
  }

  /**
   * The stored snapshot, or null when there is none — a session created
   * before this feature, or a row this build can no longer parse (which is
   * removed rather than migrated: it is a cache).
   */
  read(sessionId: string): SessionState | null {
    let raw: unknown;
    try {
      raw = this.deps.store.read(sessionId);
    } catch (error) {
      console.warn(`[acp] the snapshot of ${sessionId.slice(0, 8)} was not read: ${String(error)}`);
      return null;
    }
    if (raw === null || raw === undefined) {
      return null;
    }
    const parsed = SessionStateSchema.safeParse(raw);
    if (!parsed.success) {
      this.forget(sessionId);
      return null;
    }
    return parsed.data;
  }

  /** Cancel the pending write and drop the row: the session is gone. */
  forget(sessionId: string): void {
    this.pending.get(sessionId)?.timer.cancel();
    this.pending.delete(sessionId);
    try {
      this.deps.store.remove(sessionId);
    } catch {
      /* the row goes with the session's own (ON DELETE CASCADE) */
    }
  }
}
