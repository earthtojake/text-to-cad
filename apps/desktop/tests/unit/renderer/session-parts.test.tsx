import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@renderer/components/ui/tooltip";
import { ActivityGroup } from "@renderer/features/session/parts/ActivityRow";
import { PermissionCard } from "@renderer/features/session/parts/PermissionCard";
import { PlanCard } from "@renderer/features/session/PlanCard";
import { activityRow, foldSummary } from "@renderer/features/session/view";
import { Sidebar } from "@renderer/features/sidebar/Sidebar";
import { useAcp } from "@renderer/state/acp";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import type { PermissionRequestPart, ToolCallPart } from "@shared/acp/types";
import type { Session } from "@shared/types";

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
  useProjects.setState({ projects: [], ready: true, activeId: null, collapsed: new Set() });
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

describe("Sidebar sessions", () => {
  const session = (overrides: Partial<Session> & { id: string; title: string }): Session => ({
    projectId: "p1",
    agentId: "codex",
    cwd: "/repo",
    gitMode: "none",
    createdAt: 0,
    updatedAt: 0,
    status: "idle",
    acpSessionId: "acp",
    changedFiles: 0,
    insertions: 0,
    deletions: 0,
    archived: false,
    ...overrides,
  });

  it("lists five newest first, offers the rest behind Show more, and hides archived ones", async () => {
    const user = userEvent.setup();
    useProjects.setState({ projects: [{ id: "p1", name: "text-to-cad", path: "/repo", createdAt: 0 }], ready: true, activeId: "p1", collapsed: new Set() });
    useSessions.setState({
      sessions: [
        ...Array.from({ length: 7 }, (_, index) => session({ id: `s${index}`, title: `Session ${index}`, updatedAt: index })),
        session({ id: "gone", title: "Archived one", archived: true, updatedAt: 100 }),
      ],
      ready: true,
      activeId: "s6",
    });
    wrap(<Sidebar />);
    const rows = screen.getAllByText(/^Session \d$/).map((node) => node.textContent);
    expect(rows).toEqual(["Session 6", "Session 5", "Session 4", "Session 3", "Session 2"]);
    expect(screen.queryByText("Archived one")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Show 2 more" }));
    expect(screen.getByText("Session 0")).toBeInTheDocument();
  });

  it("shows the running spinner and the worktree glyph", () => {
    useProjects.setState({ projects: [{ id: "p1", name: "text-to-cad", path: "/repo", createdAt: 0 }], ready: true, activeId: "p1", collapsed: new Set() });
    useSessions.setState({
      sessions: [
        session({ id: "a", title: "Busy", status: "running" }),
        session({ id: "b", title: "Tree", gitMode: "worktree", branch: "hardcore/x" }),
        session({ id: "c", title: "Branch", gitMode: "checkout", branch: "main" }),
      ],
      ready: true,
      activeId: null,
    });
    wrap(<Sidebar />);
    expect(screen.getByLabelText("Working")).toBeInTheDocument();
    expect(screen.getByLabelText("Runs in a worktree")).toBeInTheDocument();
    expect(screen.getByLabelText("On main")).toBeInTheDocument();
  });
});
