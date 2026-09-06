import { describe, expect, it } from "vitest";

import {
  activityRow,
  commandLine,
  foldSummary,
  formatDuration,
  formatTokens,
  isAuthError,
  partsView,
  statusLine,
  turnView,
} from "@renderer/features/session/view";
import { initialSessionState, type Part, type SessionState, type ToolCallPart } from "@shared/acp/types";

import codexSession from "../../fixtures/acp/codex-session.jsonl?raw";
import { parseFrames, stateFromFrames } from "../shared/frames";

function call(overrides: Partial<ToolCallPart> & { id: string }): ToolCallPart {
  return {
    type: "tool_call",
    kind: "other",
    title: "",
    name: null,
    status: "completed",
    input: undefined,
    output: undefined,
    content: [],
    locations: [],
    stream: "",
    children: [],
    ...overrides,
  };
}

const edit = (id: string, file: string, status: ToolCallPart["status"] = "completed") =>
  call({ id, kind: "edit", title: `Edit ${file}`, status, content: [{ type: "diff", path: file, oldText: "a\n", newText: "a\nb\n" }] });
const read = (id: string, file: string) => call({ id, kind: "read", title: `Read ${file}`, locations: [{ path: file, line: null }] });
const run = (id: string, command: string, status: ToolCallPart["status"] = "completed") =>
  call({ id, kind: "execute", title: command, status, input: { command } });

describe("activity rows", () => {
  it("labels an edit by its file and counts the diff", () => {
    const row = activityRow(edit("e1", "src/hand.py"));
    expect(row).toMatchObject({ glyph: "edit", label: "Edited hand.py", path: "src/hand.py", insertions: 1, deletions: 0, command: null });
  });

  it("uses the progressive verb while a call is running and the failure form when it failed", () => {
    expect(activityRow(edit("e1", "a.py", "in_progress")).label).toBe("Editing a.py");
    expect(activityRow(edit("e1", "a.py", "failed")).label).toBe("Could not edit a.py");
  });

  it("puts a command's text on the row and drops a title that only repeats it", () => {
    const row = activityRow(run("c1", "ls -la"));
    expect(row.command).toBe("ls -la");
    expect(row.label).toBe("");
    const titled = activityRow(call({ id: "c2", kind: "execute", title: "Run the tests", input: { command: "npm test" } }));
    expect(titled.label).toBe("Run the tests");
    expect(titled.command).toBe("npm test");
  });

  it("treats a call whose content is an image as a viewed image", () => {
    const row = activityRow(call({ id: "i1", kind: "read", title: "Read shot.png", locations: [{ path: "shot.png", line: null }], content: [{ type: "image", data: "", mimeType: "image/png" }] }));
    expect(row.glyph).toBe("image");
    expect(row.label).toBe("Viewed shot.png");
  });

  it("keeps the first line of a multi-line command and marks the rest", () => {
    expect(commandLine("printf 'x' > a.txt\nls -la")).toBe("printf 'x' > a.txt …");
    expect(commandLine("x".repeat(200)).length).toBe(120);
    expect(commandLine("x".repeat(200)).endsWith("…")).toBe(true);
  });
});

describe("folding", () => {
  it("folds consecutive calls by kind, in order of first appearance", () => {
    const rows = [edit("e1", "a.py"), edit("e2", "b.py"), edit("e3", "c.py"), run("c1", "ls"), run("c2", "pwd")].map(activityRow);
    expect(foldSummary(rows)).toBe("Edited 3 files, ran 2 commands");
  });

  it("names a single file and uses the progressive tense while something runs", () => {
    const rows = [read("r1", "docs/notes.md"), read("r2", "docs/notes.md"), run("c1", "make", "in_progress")].map(activityRow);
    expect(foldSummary(rows)).toBe("Read notes.md, running 1 command");
  });

  it("only folds runs of two or more, and prose breaks a run", () => {
    const parts: Part[] = [
      { type: "text", text: "Looking." },
      read("r1", "a"),
      read("r2", "b"),
      { type: "text", text: "Now editing." },
      edit("e1", "c"),
      { type: "thought", text: "hm" },
      run("c1", "ls"),
      run("c2", "pwd"),
    ];
    const items = partsView(parts, false, "t");
    expect(items.map((item) => (item.kind === "activity" ? `activity:${item.summary ?? item.rows[0]!.label}` : item.kind))).toEqual([
      "text",
      "activity:Read 2 files",
      "text",
      "activity:Edited c",
      "thought",
      "activity:Ran 2 commands",
    ]);
  });

  it("leaves the plan and the commands list out of the transcript", () => {
    const parts: Part[] = [
      { type: "plan", entries: [] },
      { type: "available_commands", commands: [] },
      { type: "text", text: "x" },
    ];
    expect(partsView(parts, false, "t").map((item) => item.kind)).toEqual(["text"]);
  });

  it("marks the last text or thought of an open turn as streaming", () => {
    const items = turnView({ id: "t", role: "agent", parts: [{ type: "thought", text: "a" }, { type: "text", text: "b" }], startedAt: 0, endedAt: null, stopReason: null });
    expect(items.map((item) => ("streaming" in item ? item.streaming : null))).toEqual([false, true]);
  });
});

describe("the status line", () => {
  const base = (): SessionState => ({ ...initialSessionState("s", "codex"), status: "running" });
  const withParts = (parts: Part[]): SessionState => ({
    ...base(),
    turns: [{ id: "t", role: "agent", parts, startedAt: 0, endedAt: null, stopReason: null }],
  });

  it("names the running command, the running edit, or the thought", () => {
    expect(statusLine(withParts([run("c1", "npm test", "in_progress")]))).toBe("Running npm test");
    expect(statusLine(withParts([edit("e1", "hand.py", "in_progress")]))).toBe("Editing hand.py");
    expect(statusLine(withParts([{ type: "thought", text: "…" }]))).toBe("Thinking");
    expect(statusLine(withParts([{ type: "text", text: "…" }]))).toBeNull();
    expect(statusLine(withParts([]))).toBe("Working");
  });

  it("says waiting while a permission request is open, and nothing when idle", () => {
    expect(statusLine({ ...base(), status: "waiting" })).toBe("Waiting for your approval");
    expect(statusLine({ ...base(), status: "idle" })).toBeNull();
    expect(statusLine({ ...base(), status: "connecting" })).toBe("Connecting");
  });

  it("looks into a running subagent for what it is doing", () => {
    const state = withParts([
      { type: "subagent", sessionId: "child", name: "Explorer", task: null, state: "running", parts: [read("r1", "a.md")] },
    ]);
    expect(statusLine(state)).toBe("Read a.md");
  });
});

describe("the recorded Codex session", () => {
  const state = stateFromFrames(parseFrames(codexSession), "codex");

  it("renders the command Codex ran as one activity row with its command text", () => {
    const agentTurns = state.turns.filter((turn) => turn.role === "agent");
    const items = turnView(agentTurns[1]!);
    const activity = items.find((item) => item.kind === "activity");
    expect(activity?.kind === "activity" && activity.rows).toHaveLength(1);
    const row = activity?.kind === "activity" ? activity.rows[0]! : null;
    expect(row?.glyph).toBe("execute");
    expect(row?.command).toContain("printf");
    expect(commandLine(row!.command!)).toBe("printf '%s\\n' 'hello from codex' > hello.txt …");
    expect(row?.status).toBe("completed");
    expect(row?.part.stream).toContain("hello.txt");
  });

  it("ends each agent turn with the usage chip", () => {
    for (const turn of state.turns.filter((candidate) => candidate.role === "agent")) {
      expect(turnView(turn).at(-1)?.kind).toBe("usage");
    }
  });
});

describe("formatting", () => {
  it("rounds token counts and durations", () => {
    expect(formatTokens(950)).toBe("950");
    expect(formatTokens(19_598)).toBe("20k");
    expect(formatTokens(1_500)).toBe("1.5k");
    expect(formatTokens(2_400_000)).toBe("2.4M");
    expect(formatDuration(4_200)).toBe("4s");
    expect(formatDuration(72_000)).toBe("1m 12s");
    expect(formatDuration(3_720_000)).toBe("1h 2m");
  });

  it("recognises the adapters' authentication failures", () => {
    expect(isAuthError("session/new: Authentication required — sign in first (API Key, ChatGPT)")).toBe(true);
    expect(isAuthError("codex exited unexpectedly (code 1)")).toBe(false);
    expect(isAuthError(null)).toBe(false);
  });
});
