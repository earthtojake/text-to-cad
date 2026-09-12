import { beforeEach, describe, expect, it } from "vitest";

import { useAcp } from "@renderer/state/acp";
import { initialSessionState } from "@shared/acp/types";

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

  it("drops events for sessions it has no snapshot of", () => {
    useAcp.getState().receiveEvent("ghost", { type: "status", status: "idle", error: null, at: 1 });
    expect(useAcp.getState().sessions).toEqual({});
  });

  it("keeps a bounded tail of terminal output per terminal", () => {
    useAcp.getState().receiveTerminalOutput("s1", "t1", "a".repeat(70_000));
    useAcp.getState().receiveTerminalOutput("s1", "t1", "b");
    const tail = useAcp.getState().terminalOutput["s1/t1"]!;
    expect(tail.length).toBe(64 * 1024);
    expect(tail.endsWith("b")).toBe(true);
  });

  it("forgets a session", () => {
    useAcp.getState().receiveState("s1", initialSessionState("s1", "codex"));
    useAcp.getState().forget("s1");
    expect(useAcp.getState().sessions).toEqual({});
  });
});
