import { describe, expect, it } from "vitest";

import {
  SNAPSHOT_JSON_CAP,
  SNAPSHOT_TOOL_TEXT_CAP,
  SessionSnapshotWriter,
  trimForSnapshot,
  type SnapshotStore,
} from "@main/acp/snapshots";
import { initialSessionState, type Part, type SessionState, type Turn } from "@shared/acp/types";

/**
 * The picture of a transcript a session paints from while its agent
 * reconnects (README, "Opening a session"). Three things are worth a test:
 * the writes are coalesced (a streaming turn is thousands of states a
 * minute), the bulk is capped (a `Read` of a big file is not worth keeping),
 * and a row this build cannot parse is dropped rather than trusted.
 */

/** A store in a Map, with a count of the writes it was asked for. */
function memoryStore(): SnapshotStore & { rows: Map<string, string>; writes: number } {
  const rows = new Map<string, string>();
  const store = {
    rows,
    writes: 0,
    read: (id: string) => {
      const json = rows.get(id);
      return json === undefined ? null : JSON.parse(json);
    },
    write: (id: string, json: string) => {
      store.writes += 1;
      rows.set(id, json);
    },
    remove: (id: string) => {
      rows.delete(id);
    },
  };
  return store;
}

/** A scheduler the test fires by hand, in place of `setTimeout`. */
function manualSchedule() {
  const pending: (() => void)[] = [];
  return {
    schedule: (run: () => void) => {
      pending.push(run);
      return {
        cancel: () => {
          const at = pending.indexOf(run);
          if (at >= 0) {
            pending.splice(at, 1);
          }
        },
      };
    },
    /** Run everything still scheduled. */
    fire: () => {
      for (const run of pending.splice(0)) {
        run();
      }
    },
    get size() {
      return pending.length;
    },
  };
}

function toolCall(overrides: Partial<Extract<Part, { type: "tool_call" }>> = {}): Part {
  return {
    type: "tool_call",
    id: "call-1",
    kind: "read",
    title: "Read big.txt",
    name: "Read",
    status: "completed",
    input: {},
    output: null,
    content: [],
    locations: [],
    stream: "",
    children: [],
    ...overrides,
  };
}

function turn(id: string, parts: Part[]): Turn {
  return { id, role: "agent", parts, startedAt: 1, endedAt: 2, stopReason: "end_turn" };
}

function stateWith(turns: Turn[]): SessionState {
  return { ...initialSessionState("s1", "claude-code"), turns };
}

describe("trimForSnapshot", () => {
  it("caps the four fields of a tool call that carry bulk, and says how much it dropped", () => {
    const big = "x".repeat(SNAPSHOT_TOOL_TEXT_CAP * 4);
    const trimmed = trimForSnapshot(
      stateWith([
        turn("t1", [
          toolCall({
            stream: big,
            content: [
              { type: "text", text: big },
              { type: "diff", path: "a.py", oldText: big, newText: big },
            ],
            input: { text: big },
            output: { text: big },
          }),
        ]),
      ]),
    );
    const part = trimmed.turns[0]!.parts[0]!;
    if (part.type !== "tool_call") {
      throw new Error("the part is a tool call");
    }
    expect(part.stream.length).toBeLessThan(big.length);
    expect(part.stream).toContain("KB dropped from this snapshot");
    const text = part.content[0]!;
    expect(text.type === "text" && text.text.length).toBeLessThan(big.length);
    const diff = part.content[1]!;
    expect(diff.type === "diff" && diff.newText.length).toBeLessThan(big.length);
    expect(diff.type === "diff" && (diff.oldText ?? "").length).toBeLessThan(big.length);
    // An `unknown` payload is dropped rather than truncated: half a JSON
    // blob is not JSON.
    expect(part.input).toBeNull();
    expect(part.output).toBeNull();
  });

  it("leaves a small tool call exactly as it was, nested calls included", () => {
    const child = toolCall({ id: "child", stream: "ok", input: { path: "a" } });
    const state = stateWith([turn("t1", [toolCall({ children: [child] })])]);
    expect(trimForSnapshot(state).turns).toEqual(state.turns);
  });

  /**
   * A transcript is not a bounded thing, and a session with two thousand
   * small turns would be megabytes with nothing to cap per part. The oldest
   * go; the newest never does, because a snapshot of nothing is a spinner.
   */
  it("drops the oldest turns until the whole snapshot fits, and keeps the newest", () => {
    const filler = "y".repeat(SNAPSHOT_TOOL_TEXT_CAP - 100);
    const many = Array.from({ length: 400 }, (_, index) =>
      turn(`t${index}`, [{ type: "text", text: filler }]),
    );
    const trimmed = trimForSnapshot(stateWith(many));
    expect(JSON.stringify(trimmed).length).toBeLessThanOrEqual(SNAPSHOT_JSON_CAP);
    expect(trimmed.turns.length).toBeLessThan(many.length);
    expect(trimmed.turns.at(-1)!.id).toBe("t399");
  });

  it("keeps one turn even when that one turn is over the budget", () => {
    const enormous = "z".repeat(SNAPSHOT_JSON_CAP * 2);
    const trimmed = trimForSnapshot(stateWith([turn("t1", [{ type: "text", text: enormous }])]));
    expect(trimmed.turns).toHaveLength(1);
  });

  /**
   * The three fields that only mean something while a connection is up. A
   * stored `closed` would grey the composer of a session that is about to be
   * live; a stored `error` would show last week's failure beside a working
   * thread; and a permission request cannot be answered without the agent
   * that asked it.
   */
  it("neutralises the status, the error and the pending permissions", () => {
    const live: SessionState = {
      ...initialSessionState("s1", "codex"),
      status: "closed",
      error: "the agent exited",
      pendingPermissions: [
        {
          requestId: "r1",
          acpSessionId: "acp-1",
          toolCallId: "call-1",
          title: null,
          description: null,
          kind: null,
          input: null,
          options: [],
        },
      ],
    };
    expect(trimForSnapshot(live)).toMatchObject({ status: "idle", error: null, pendingPermissions: [] });
  });
});

describe("SessionSnapshotWriter", () => {
  it("coalesces a burst of states into one write of the last one", () => {
    const store = memoryStore();
    const timers = manualSchedule();
    const writer = new SessionSnapshotWriter({ store, schedule: timers.schedule });

    for (let index = 0; index < 50; index += 1) {
      writer.save("s1", stateWith([turn(`t${index}`, [{ type: "text", text: `chunk ${index}` }])]));
    }
    expect(store.writes).toBe(0);
    expect(timers.size).toBe(1);
    timers.fire();
    expect(store.writes).toBe(1);
    expect(writer.read("s1")!.turns.at(-1)!.id).toBe("t49");
  });

  it("keeps one pending write per session", () => {
    const store = memoryStore();
    const timers = manualSchedule();
    const writer = new SessionSnapshotWriter({ store, schedule: timers.schedule });
    writer.save("s1", stateWith([turn("a", [])]));
    writer.save("s2", stateWith([turn("b", [])]));
    expect(timers.size).toBe(2);
    timers.fire();
    expect(store.rows.size).toBe(2);
  });

  it("flush writes the pending state at once — the adapter is going away", () => {
    const store = memoryStore();
    const timers = manualSchedule();
    const writer = new SessionSnapshotWriter({ store, schedule: timers.schedule });
    writer.save("s1", stateWith([turn("t1", [])]));
    writer.flush("s1");
    expect(store.writes).toBe(1);
    // The scheduled write was cancelled, not left to fire a second time.
    timers.fire();
    expect(store.writes).toBe(1);
  });

  it("flushAll files every session on quit", () => {
    const store = memoryStore();
    const writer = new SessionSnapshotWriter({ store, schedule: manualSchedule().schedule });
    writer.save("s1", stateWith([turn("a", [])]));
    writer.save("s2", stateWith([turn("b", [])]));
    writer.flushAll();
    expect(store.rows.size).toBe(2);
  });

  it("forget cancels the pending write and drops the row", () => {
    const store = memoryStore();
    const timers = manualSchedule();
    const writer = new SessionSnapshotWriter({ store, schedule: timers.schedule });
    writer.save("s1", stateWith([turn("t1", [])]));
    writer.flush("s1");
    writer.save("s1", stateWith([turn("t2", [])]));
    writer.forget("s1");
    timers.fire();
    expect(store.rows.has("s1")).toBe(false);
    expect(writer.read("s1")).toBeNull();
  });

  /** It is a cache: a row this build cannot read goes, and the session gets the spinner. */
  it("drops a row that no longer parses instead of trusting it", () => {
    const store = memoryStore();
    store.rows.set("s1", JSON.stringify({ sessionId: "s1", turns: "not an array" }));
    const writer = new SessionSnapshotWriter({ store, schedule: manualSchedule().schedule });
    expect(writer.read("s1")).toBeNull();
    expect(store.rows.has("s1")).toBe(false);
  });

  it("returns null for a session that has no snapshot at all", () => {
    const writer = new SessionSnapshotWriter({ store: memoryStore(), schedule: manualSchedule().schedule });
    expect(writer.read("never-connected")).toBeNull();
  });

  /** A snapshot is a nicety; a session must not fail to run because its picture could not be filed. */
  it("survives a store that throws", () => {
    const store: SnapshotStore = {
      read: () => {
        throw new Error("the database is closed");
      },
      write: () => {
        throw new Error("the database is closed");
      },
      remove: () => undefined,
    };
    const writer = new SessionSnapshotWriter({ store, schedule: manualSchedule().schedule });
    expect(() => writer.save("s1", stateWith([]))).not.toThrow();
    expect(() => writer.flush("s1")).not.toThrow();
    expect(writer.read("s1")).toBeNull();
  });
});
