import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAcp } from "@renderer/state/acp";
import { useSessions } from "@renderer/state/sessions";
import { initialSessionState, type SessionState } from "@shared/acp/types";
import type { Session } from "@shared/types";

describe("the acp store", () => {
  beforeEach(() => {
    useAcp.setState({ sessions: {}, terminalOutput: {} });
  });

  it("takes a snapshot and then folds events through the shared reducer", () => {
    const snapshot = { ...initialSessionState("s1", "codex"), acpSessionId: "acp-1", status: "idle" as const };
    useAcp.getState().receiveState("s1", snapshot);
    useAcp.getState().receiveEvent("s1", { type: "prompt/start", turnId: "t1", content: [{ type: "text", text: "hi" }], at: 1 });
    useAcp.getState().receiveEvent("s1", {
      type: "session/update",
      acpSessionId: "acp-1",
      update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "ok" } },
      at: 2,
    });
    const state = useAcp.getState().sessions.s1!;
    expect(state.status).toBe("running");
    expect(state.turns).toHaveLength(2);
    expect(state.turns[1]?.parts).toEqual([{ type: "text", text: "ok" }]);
  });

  it("clears a reconnect failure when a state says the agent is up, and keeps it for one that does not", () => {
    useAcp.setState({ loadErrors: { s1: "Claude Code exited", s2: "Claude Code exited" } });
    useAcp.getState().receiveState("s1", { ...initialSessionState("s1", "codex"), status: "idle" });
    expect(useAcp.getState().loadErrors).toEqual({ s2: "Claude Code exited" });
    useAcp.getState().receiveState("s2", { ...initialSessionState("s2", "codex"), status: "closed" });
    expect(useAcp.getState().loadErrors).toEqual({ s2: "Claude Code exited" });
  });

  it("drops events for sessions it has no snapshot of", () => {
    useAcp.getState().receiveEvent("ghost", { type: "status", status: "idle", error: null, at: 1 });
    expect(useAcp.getState().sessions).toEqual({});
  });

  it("keeps a bounded tail of terminal output per terminal", () => {
    useAcp.getState().receiveState("s1", initialSessionState("s1", "codex"));
    useAcp.getState().receiveTerminalOutput("s1", "t1", "a".repeat(70_000));
    useAcp.getState().receiveTerminalOutput("s1", "t1", "b");
    const tail = useAcp.getState().terminalOutput["s1/t1"]!;
    expect(tail.length).toBe(64 * 1024);
    expect(tail.endsWith("b")).toBe(true);
  });

  // A state landed while the command ran (a reload, a background reconnect): its output so far is unknown,
  // so it is cold. An exit seen here with nothing ever written makes it silent after all; one that had
  // written something (before this store looked) stays "not kept".
  it("un-colds a terminal seen to exit having written nothing, and only that one", () => {
    const withTerminals = (state: SessionState): SessionState => ({
      ...state,
      turns: [
        {
          id: "a1",
          role: "agent",
          parts: ["t1", "t2"].map((terminalId) => ({
            type: "tool_call" as const,
            id: `call-${terminalId}`,
            title: "run",
            kind: "execute" as const,
            status: "in_progress" as const,
            content: [{ type: "terminal" as const, terminalId }],
            children: [],
          })),
        },
      ] as unknown as SessionState["turns"],
    });
    useAcp.getState().receiveState("s1", withTerminals(initialSessionState("s1", "codex")));
    expect(Object.keys(useAcp.getState().coldTerminals).sort()).toEqual(["s1/t1", "s1/t2"]);
    useAcp.getState().receiveTerminalOutput("s1", "t1", "", true);
    useAcp.getState().receiveTerminalOutput("s1", "t2", "", false);
    expect(useAcp.getState().coldTerminals).toEqual({ "s1/t2": true });
  });

  it("ignores terminal output for a session it does not hold, or has let go of", () => {
    useAcp.getState().receiveTerminalOutput("ghost", "t1", "late");
    useAcp.getState().receiveState("s1", initialSessionState("s1", "codex"));
    useAcp.getState().receiveTerminalOutput("s1", "t1", "kept");
    useAcp.getState().forget("s1");
    useAcp.getState().receiveTerminalOutput("s1", "t1", "late");
    expect(useAcp.getState().terminalOutput).toEqual({});
  });

  it("forgets a session", () => {
    useAcp.getState().receiveState("s1", initialSessionState("s1", "codex"));
    useAcp.getState().forget("s1");
    expect(useAcp.getState().sessions).toEqual({});
  });
});

describe("what the acp store lets go of", () => {
  const row = (id: string, archived = false) => ({ id, projectId: "p1", agentId: "codex", title: id, cwd: "/p1", status: "idle", archived }) as unknown as Session;
  const live = (id: string) => ({ ...initialSessionState(id, "codex"), status: "idle" as const });

  beforeEach(() => {
    useSessions.setState({ sessions: [row("s1"), row("s2")], activeId: "s2", ready: true });
    useAcp.setState({ sessions: { s1: live("s1"), s2: live("s2") }, terminalOutput: {}, loading: {}, reconnecting: {}, loadErrors: {} });
  });

  it("forgets a session whose row is deleted", () => {
    useSessions.getState().receive([row("s2")]);
    expect(Object.keys(useAcp.getState().sessions)).toEqual(["s2"]);
  });

  it("forgets a session when it is archived", () => {
    useSessions.getState().receive([row("s1", true), row("s2")]);
    expect(Object.keys(useAcp.getState().sessions)).toEqual(["s2"]);
  });

  it("takes a forgotten session's terminal output with it, and only its", () => {
    useAcp.getState().receiveTerminalOutput("s1", "t1", "one");
    useAcp.getState().receiveTerminalOutput("s1", "t2", "two");
    useAcp.getState().receiveTerminalOutput("s2", "t1", "kept");
    useAcp.getState().forget("s1");
    expect(useAcp.getState().terminalOutput).toEqual({ "s2/t1": "kept" });
  });

  it("drops a closed session that is not on screen — the snapshot repaints it — and keeps the one that is", () => {
    const closed = { type: "status", status: "closed", error: null, at: 1 } as const;
    useAcp.getState().receiveEvent("s1", closed);
    useAcp.getState().receiveEvent("s2", closed);
    expect(Object.keys(useAcp.getState().sessions)).toEqual(["s2"]);
    useSessions.getState().setActive("s1");
    expect(useAcp.getState().sessions).toEqual({});
  });

  describe("a session archived while it loads", () => {
    const sessionsApi = window.textToCad.sessions as unknown as Record<string, unknown>;
    const deferred = <T,>() => {
      let settle!: { resolve: (value: T) => void; reject: (error: Error) => void };
      const promise = new Promise<T>((resolve, reject) => (settle = { resolve, reject }));
      return { promise, ...settle };
    };
    const archiveS1 = () => useSessions.getState().receive([row("s1", true), row("s2")]);

    beforeEach(() => useAcp.setState({ sessions: {} }));

    it("is not brought back by the load's answer", async () => {
      const answer = deferred<unknown>();
      sessionsApi.load = vi.fn(() => answer.promise);
      const loading = useAcp.getState().load("s1");
      archiveS1();
      answer.resolve(live("s1"));
      await loading;
      expect(useAcp.getState().sessions).toEqual({});
    });

    it("is not given the load's failure", async () => {
      const answer = deferred<unknown>();
      sessionsApi.load = vi.fn(() => answer.promise);
      const loading = useAcp.getState().load("s1");
      archiveS1();
      answer.reject(new Error("gone"));
      await loading;
      expect(useAcp.getState().loadErrors).toEqual({});
    });

    it("is not painted by the snapshot that was on its way", async () => {
      const snapshot = deferred<unknown>();
      sessionsApi.state = vi.fn(() => snapshot.promise);
      sessionsApi.load = vi.fn(async () => live("s1"));
      const opening = useAcp.getState().ensureLoaded("s1");
      archiveS1();
      snapshot.resolve({ state: live("s1"), live: true });
      await opening;
      expect(useAcp.getState().sessions).toEqual({});
    });
  });
});

describe("Disconnect agent", () => {
  it("keeps the transcript on screen, marked closed", async () => {
    const sessionsApi = window.textToCad.sessions as unknown as Record<string, unknown>;
    sessionsApi.close = vi.fn(async () => undefined);
    useAcp.setState({ sessions: {}, terminalOutput: {}, loading: {}, reconnecting: {}, loadErrors: {} });
    useAcp.getState().receiveState("s1", { ...initialSessionState("s1", "codex"), status: "idle" as const });
    useAcp.getState().receiveEvent("s1", { type: "prompt/start", turnId: "t1", content: [{ type: "text", text: "hi" }], at: 1 });
    const turns = useAcp.getState().sessions.s1!.turns;
    expect(turns.length).toBeGreaterThan(0);

    await useAcp.getState().close("s1");

    const held = useAcp.getState().sessions.s1;
    expect(held?.status).toBe("closed");
    // Kept, not cleared: the same turns, the one that was streaming now ended.
    expect(held?.turns.map((turn) => turn.id)).toEqual(turns.map((turn) => turn.id));
    // Turns that had already ended keep their identity across the close: no re-render of the history.
    expect(held?.turns[0]).toBe(turns[0]);
    expect(held?.turns.at(-1)?.endedAt).not.toBeNull();
  });

  describe("during a Reconnect", () => {
    const sessionsApi = window.textToCad.sessions as unknown as Record<string, unknown>;
    const deferred = <T,>() => {
      let settle!: { resolve: (value: T) => void; reject: (error: Error) => void };
      const promise = new Promise<T>((resolve, reject) => (settle = { resolve, reject }));
      return { promise, ...settle };
    };

    beforeEach(() => {
      sessionsApi.close = vi.fn(async () => undefined);
      useAcp.setState({ sessions: {}, terminalOutput: {}, loading: {}, reconnecting: {}, loadErrors: {} });
      useAcp.getState().receiveState("s1", { ...initialSessionState("s1", "codex"), status: "closed" as const });
    });

    it("is not painted ready by the load's answer", async () => {
      const answer = deferred<unknown>();
      sessionsApi.load = vi.fn(() => answer.promise);
      const reconnecting = useAcp.getState().load("s1");
      await useAcp.getState().close("s1");
      answer.resolve({ ...initialSessionState("s1", "codex"), status: "idle" as const });
      await reconnecting;
      expect(useAcp.getState().sessions.s1?.status).toBe("closed");
    });

    it("is not painted ready by the state main broadcasts at the end of the load", async () => {
      const answer = deferred<unknown>();
      sessionsApi.load = vi.fn(() => answer.promise);
      const reconnecting = useAcp.getState().load("s1");
      await useAcp.getState().close("s1");
      // The bridge's `session.state`, which main sends ahead of the load's reply.
      useAcp.getState().receiveState("s1", { ...initialSessionState("s1", "codex"), status: "idle" as const });
      expect(useAcp.getState().sessions.s1?.status).toBe("closed");
      answer.resolve({ ...initialSessionState("s1", "codex"), status: "idle" as const });
      await reconnecting;
      expect(useAcp.getState().sessions.s1?.status).toBe("closed");
    });

    it("is not given the load's failure", async () => {
      const answer = deferred<unknown>();
      sessionsApi.load = vi.fn(() => answer.promise);
      const reconnecting = useAcp.getState().load("s1");
      await useAcp.getState().close("s1");
      answer.reject(new Error("the agent went away"));
      await reconnecting;
      expect(useAcp.getState().loadErrors).toEqual({});
      expect(useAcp.getState().sessions.s1?.status).toBe("closed");
    });
  });
});

describe("opening a session main has just created", () => {
  const sessionsApi = window.textToCad.sessions as unknown as Record<string, unknown>;
  const live = () => ({ ...initialSessionState("s1", "codex"), status: "idle" as const });

  beforeEach(() => {
    useAcp.setState({ sessions: {}, terminalOutput: {}, loading: {}, reconnecting: {}, loadErrors: {} });
  });

  /**
   * A new session's first `session.state` broadcast reaches the renderer while the open's own
   * snapshot request is still on the way, so the session is held before that answers. The answer
   * says main's connection is live: nothing to reconnect. A `load` there marks the session
   * `reconnecting` — every turn event is dropped until its reply — and repaints from a snapshot
   * older than the prompt sent meanwhile, so that prompt never showed (CI, the full-access spec's
   * second prompt).
   */
  it("does not reconnect a live session that a broadcast painted while its snapshot was on the way", async () => {
    let answer!: (value: unknown) => void;
    sessionsApi.state = vi.fn(() => new Promise((resolve) => (answer = resolve)));
    sessionsApi.load = vi.fn(async () => live());

    const opening = useAcp.getState().ensureLoaded("s1");
    useAcp.getState().receiveState("s1", live());
    answer({ state: live(), live: true });
    await opening;

    expect(sessionsApi.load).not.toHaveBeenCalled();
    expect(useAcp.getState().reconnecting).toEqual({});
    expect(useAcp.getState().loading).toEqual({});
    // So the turn that starts right after is kept.
    useAcp.getState().receiveEvent("s1", { type: "prompt/start", turnId: "t1", content: [{ type: "text", text: "hi" }], at: 1 });
    expect(useAcp.getState().sessions.s1?.turns).toHaveLength(2);
  });
});
