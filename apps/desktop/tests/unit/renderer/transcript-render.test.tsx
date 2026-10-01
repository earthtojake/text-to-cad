import { beforeEach, describe, expect, it, vi } from "vitest";
import { render } from "@testing-library/react";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { Transcript } from "@renderer/features/session/Transcript";
import { initialSessionState, type SessionState, type ToolCallPart, type Turn } from "@shared/acp/types";

// Each turn's body, counted: what a turn draws again is what its parts list
// is handed again. The real list's markdown, activity rows and diff badges
// are what a render costs; which turns render is what is measured here.
const drawn = vi.hoisted(() => [] as Array<{ turn: string; parts: Turn["parts"] }>);
vi.mock("@renderer/features/session/parts/PartsList", () => ({
  PartsList: ({ prefix, parts }: { prefix: string; parts: Turn["parts"] }) => {
    drawn.push({ turn: prefix, parts });
    return null;
  },
}));

const call = (id: string, overrides: Partial<ToolCallPart> = {}): ToolCallPart => ({
  type: "tool_call",
  id,
  kind: "other",
  title: id,
  name: null,
  status: "completed",
  input: undefined,
  output: undefined,
  content: [],
  locations: [],
  stream: "",
  children: [],
  ...overrides,
});

const agent = (id: string, parts: Turn["parts"], endedAt: number | null): Turn => ({
  id,
  role: "agent",
  parts,
  startedAt: 1,
  endedAt,
  stopReason: endedAt === null ? null : "end_turn",
});

const view = (state: SessionState) => (
  <TooltipProvider>
    <Transcript onReconnect={() => {}} onRetry={() => {}} state={state} />
  </TooltipProvider>
);
const times = (turn: string) => drawn.filter((entry) => entry.turn === turn).length;

beforeEach(() => {
  drawn.length = 0;
});

describe("the transcript's live region", () => {
  it("is busy while a turn streams and not once it has ended", () => {
    const open: SessionState = {
      ...initialSessionState("s1", "codex"),
      status: "running",
      turns: [agent("t1", [{ type: "text", text: "Now" }], null)],
    };
    const { container, rerender } = render(view(open));
    expect(container.querySelector('[role="log"]')?.getAttribute("aria-busy")).toBe("true");
    rerender(view({ ...open, status: "idle", turns: [agent("t1", [{ type: "text", text: "Now" }], 2)] }));
    expect(container.querySelector('[role="log"]')?.getAttribute("aria-busy")).not.toBe("true");
  });

  it("is not busy while the turn waits on a permission answer", () => {
    const { container } = render(
      view({ ...initialSessionState("s1", "codex"), status: "waiting", turns: [agent("t1", [], null)] }),
    );
    expect(container.querySelector('[role="log"]')?.getAttribute("aria-busy")).not.toBe("true");
  });
});

describe("the transcript while the last turn streams", () => {
  it("draws the streaming turn again and leaves the earlier ones alone", () => {
    const first = agent("t1", [{ type: "text", text: "Done." }, call("e1", { kind: "edit" })], 2);
    const state: SessionState = {
      ...initialSessionState("s1", "codex"),
      status: "running",
      turns: [first, agent("t2", [{ type: "text", text: "Now" }], null)],
    };
    const { rerender } = render(view(state));
    expect(times("t1")).toBe(1);
    expect(times("t2")).toBe(1);

    // Tokens on the last turn: the reducer replaces that turn and keeps the first.
    for (const text of ["Now the", "Now the second", "Now the second file"]) {
      rerender(view({ ...state, turns: [first, agent("t2", [{ type: "text", text }], null)] }));
    }
    expect(times("t2")).toBe(4);
    expect(times("t1")).toBe(1);
  });

  it("draws a turn again when a subagent's child inside it changes", () => {
    const running = call("child", { status: "in_progress" });
    const first = agent("t1", [call("task", { kind: "think", status: "in_progress", children: [running] })], null);
    const state: SessionState = { ...initialSessionState("s1", "claude"), status: "running", turns: [first] };
    const { rerender } = render(view(state));
    expect(times("t1")).toBe(1);

    // The child finishes: the reducer replaces the child, its parent part
    // and the turn that holds them, so the turn is not the one memoised.
    const finished = agent("t1", [call("task", { kind: "think", status: "in_progress", children: [{ ...running, status: "completed" }] })], null);
    rerender(view({ ...state, turns: [finished] }));
    expect(times("t1")).toBe(2);
    const task = drawn.at(-1)!.parts[0] as ToolCallPart;
    expect(task.children[0]).toMatchObject({ id: "child", status: "completed" });
  });
});
