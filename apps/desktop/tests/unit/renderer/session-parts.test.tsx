import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import { ActivityGroup } from "@renderer/features/session/parts/ActivityRow";
import { PermissionCard } from "@renderer/features/session/parts/PermissionCard";
import { PlanCard } from "@renderer/features/session/PlanCard";
import { activityRow, foldSummary } from "@renderer/features/session/view";
import { useAcp } from "@renderer/state/acp";
import { useSessions } from "@renderer/state/sessions";
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
  useAcp.setState({ sessions: {}, terminalOutput: {}, loading: {}, loadErrors: {} });
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
    (window.hardcore.sessions as unknown as { respondPermission: unknown }).respondPermission = respond;
    wrap(<PermissionCard part={part} sessionId="s1" />);
    expect(screen.getByText("Run ls?")).toBeInTheDocument();
    expect(screen.getByText("Lists the directory.")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button").map((button) => button.textContent);
    expect(buttons).toEqual(["Yes", "Yes, always", "No"]);
    await user.click(screen.getByRole("button", { name: "Yes, always" }));
    expect(respond).toHaveBeenCalledWith({ id: "s1", requestId: "perm-1", optionId: "allow-always" });
  });

  it("folds to the decision once answered", () => {
    wrap(<PermissionCard part={{ ...part, outcome: { state: "selected", optionId: "reject" } }} sessionId="s1" />);
    expect(screen.getByText(/Rejected — No/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
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
        running={false}
        startedAt={null}
      />,
    );
    expect(screen.getByText("Write the script")).toBeInTheDocument();
    expect(screen.getByText("1 of 3 done")).toBeInTheDocument();
  });
});
