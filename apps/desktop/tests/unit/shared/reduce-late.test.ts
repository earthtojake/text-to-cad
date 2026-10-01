import { describe, expect, it } from "vitest";

import { reduce, turnFactsFrom } from "@shared/acp/reduce";
import { initialSessionState, type SessionEvent, type SessionState, type Turn } from "@shared/acp/types";

const at = 1_000;
const root = "root-session";
const chunk = (state: SessionState, text: string) =>
  reduce(state, {
    type: "session/update",
    acpSessionId: root,
    update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text } } as never as SessionEvent extends { update: infer U } ? U : never,
    at,
  });

function stopped(): SessionState {
  let state = reduce(initialSessionState("s1", "fake"), {
    type: "session/connected", acpSessionId: root, modes: null, configOptions: null, loading: false, at,
  } as never);
  state = reduce(state, { type: "prompt/start", turnId: "t1", content: [{ type: "text", text: "hi" }], at });
  state = chunk(state, "Working on it.");
  return reduce(state, { type: "prompt/end", stopReason: "cancelled", usage: null, at });
}

it("marks a chunk that arrives after the turn ended as late, from where it begins", () => {
  const state = chunk(stopped(), "Background task finished.");
  const turn = state.turns.at(-1)!;
  expect(turn.stopReason).toBe("cancelled");
  expect(turn.parts).toHaveLength(2);
  expect(turn.lateFrom).toBe(1);
  // The chunks behind the first join it, and the mark stays where it was.
  expect(chunk(state, " More.").turns.at(-1)).toMatchObject({ lateFrom: 1, parts: [{ text: "Working on it." }, { text: "Background task finished. More." }] });
});

it("leaves a turn that took nothing late unmarked", () => {
  expect(stopped().turns.at(-1)!.lateFrom).toBeUndefined();
});

describe("turnFactsFrom (what a session/load restores from the stored transcript)", () => {
  const turn = (role: "user" | "agent", text: string, extra: Partial<Turn> = {}): Turn => ({
    id: "t", role, parts: [{ type: "text", text }], startedAt: 1, endedAt: 2, stopReason: role === "agent" ? "end_turn" : null, ...extra,
  });

  it("takes a stored stop reason and lateFrom where the replay has the same parts", () => {
    const replayed = [turn("user", "q"), turn("agent", "a")];
    const stored = [turn("user", "q"), turn("agent", "a", { stopReason: "cancelled", lateFrom: 0 })];
    expect(turnFactsFrom(replayed, stored)).toEqual([{ turn: 1, stopReason: "cancelled", lateFrom: 0 }]);
  });

  it("splits the text the replay merged where the stored text before lateFrom ends", () => {
    const stored = [
      turn("user", "q"),
      turn("agent", "", {
        parts: [{ type: "text", text: "Working on it." }, { type: "text", text: "Background task finished." }],
        stopReason: "cancelled",
        lateFrom: 1,
      }),
    ];
    const replayed = [turn("user", "q"), turn("agent", "Working on it.Background task finished.")];
    const facts = turnFactsFrom(replayed, stored);
    expect(facts).toEqual([{ turn: 1, stopReason: "cancelled", lateFrom: 1, split: { part: 0, at: 14 } }]);

    let state = reduce(initialSessionState("s1", "fake"), { type: "session/loaded", at } as never);
    state = { ...state, turns: replayed };
    const restored = reduce(state, { type: "turns/restored", facts, at }).turns[1]!;
    expect(restored).toMatchObject({
      stopReason: "cancelled",
      lateFrom: 1,
      parts: [{ text: "Working on it." }, { text: "Background task finished." }],
    });
  });

  it("restores neither fact when the stored text is not a prefix of the replayed text", () => {
    const stored = [
      turn("user", "q"),
      turn("agent", "", {
        parts: [{ type: "text", text: "Working on it." }, { type: "text", text: "Background task finished." }],
        stopReason: "cancelled",
        lateFrom: 1,
      }),
    ];
    expect(turnFactsFrom([turn("user", "q"), turn("agent", "Something else entirely, longer.")], stored)).toEqual([]);
  });

  it("stops at a user turn that says something else", () => {
    const replayed = [turn("user", "q"), turn("agent", "a")];
    expect(turnFactsFrom(replayed, [turn("user", "other"), turn("agent", "a", { stopReason: "cancelled" })])).toEqual([]);
  });
});
