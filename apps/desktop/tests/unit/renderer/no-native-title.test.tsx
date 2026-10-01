import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";

import { ReviewTab } from "@renderer/features/explorer/ReviewTab";
import { TabStrip } from "@renderer/features/explorer/TabStrip";
import type { FileDiff, GitStatus } from "@renderer/features/explorer/types";
import { Composer } from "@renderer/features/session/Composer";
import { AnnotationsChip } from "@renderer/features/session/composer/AnnotationsChip";
import { ContextMeter } from "@renderer/features/session/ContextMeter";
import { PathLink, TranscriptScopeContext } from "@renderer/features/session/links/PathLink";
import { ActivityRowView } from "@renderer/features/session/parts/ActivityRow";
import { PermissionCard } from "@renderer/features/session/parts/PermissionCard";
import { SubagentRow } from "@renderer/features/session/parts/SubagentRow";
import { SessionHeader } from "@renderer/features/session/SessionHeader";
import { AgentDrawer } from "@renderer/features/settings/AgentDrawer";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { Sidebar } from "@renderer/features/sidebar/Sidebar";
import { StatusLine } from "@renderer/features/session/StatusLine";
import { Transcript } from "@renderer/features/session/Transcript";
import { activityRow } from "@renderer/features/session/view";
import { useAgents } from "@renderer/state/agents";
import { useComposer } from "@renderer/state/composer";
import { useExplorer } from "@renderer/state/explorer";
import { usePathLinks } from "@renderer/state/path-links";
import { useProjects } from "@renderer/state/projects";
import { useRuntime } from "@renderer/state/runtime";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { SETTINGS_SECTIONS, useUi } from "@renderer/state/ui";
import type { AgentStatus } from "@shared/agents";
import { initialSessionState, type SessionState, type ToolCallPart } from "@shared/acp/types";
import { defaultSettings, type Session } from "@shared/types";

/**
 * The session's interface hints are the kit's `TooltipHint`, never a native `title`
 * (packages/ui/README.md): a native tooltip cannot be styled, ignores the 400ms hint delay and
 * reads twice to a screen reader beside the label. One pass over every control the session draws,
 * and over the other desktop screens the rule covers: the sidebar, Settings and the agent drawer,
 * the explorer's tab strip (`TabStrip`) and the review tab (`ReviewTab`). A new screen is added here.
 */

// Monaco draws nothing readable in jsdom; the review's diff is stood in for.
vi.mock("@renderer/features/explorer/review-diff", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  ReviewDiff: ({ diff }: { diff: FileDiff }) => <pre>{diff.after}</pre>,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), dismiss: vi.fn(), info: vi.fn() } }));

const noRects = () => Object.assign([], { item: () => null }) as unknown as DOMRectList;
Range.prototype.getClientRects ??= noRects;
Range.prototype.getBoundingClientRect ??= () => new DOMRect();
(Text.prototype as unknown as { getClientRects: () => DOMRectList }).getClientRects ??= noRects;
URL.createObjectURL = () => "blob:no-native-title";
URL.revokeObjectURL = () => {};

const SESSION = { id: "s1", projectId: "p", agentId: "codex", cwd: "/p", title: "Bracket", status: "idle", archived: false } as unknown as Session;
const scope = { projectId: "p", root: null };

function call(overrides: Partial<ToolCallPart> & { id: string }): ToolCallPart {
  return { type: "tool_call", kind: "other", title: "", name: null, status: "completed", input: undefined, output: undefined, content: [], locations: [], stream: "", children: [], ...overrides };
}

beforeEach(() => {
  useProjects.setState({ projects: [{ id: "p", name: "p", path: "/p", createdAt: 0 }], activeId: "p" });
  useComposer.setState({ drafts: {}, annotations: {}, acceptedContexts: {}, referenceLabels: {}, pendingFiles: {}, draftRoots: {}, queues: {}, sending: {} });
  usePathLinks.setState({ kinds: {} });
  useExplorer.setState({ sessionId: "s1", projectId: "p", root: null, tabs: [], activeId: null, ready: true, collapsed: true, cadSelection: null, reveal: null });
  (window.textToCad.explorer as unknown as Record<string, unknown>).exists = vi.fn(async () => ({ "models/x.step": "file" }));
});

const titled = () =>
  [...document.querySelectorAll("button, a, [role=button], [role=menuitem], [role=menuitemradio]")]
    .filter((control) => control.hasAttribute("title"))
    .map((control) => control.outerHTML.slice(0, 120));

it("no control in a session carries a native title", async () => {
  const user = userEvent.setup();
  const annotation = { id: "a1", text: "fillet it", references: [] };
  useComposer.getState().setDraft("s1", "look at models/x.step#o1 ");
  // The session's row, so the reference chip has a project to open in and is a button.
  useSessions.setState({ sessions: [SESSION], ready: true, activeId: "s1" });
  const view = render(
    <TooltipProvider>
    <TranscriptScopeContext.Provider value={scope}>
      <SessionHeader session={SESSION} title="Bracket" />
      <ContextMeter lastTurnUsage={null} rateLimits={{}} sessionId="s1" sessionUsage={null} usage={{ used: 1200, size: 200_000, cost: null, breakdown: null }} />
      <Composer chips={null} commands={[]} onSubmit={vi.fn()} sessionId="s1" status="ready" />
      <AnnotationsChip annotations={[annotation]} onEdit={vi.fn()} onRemove={vi.fn()} onRemoveOne={vi.fn()} scope={null} />
      <PathLink href="./models/x.step#o1">models/x.step#o1</PathLink>
      <PermissionCard
        part={{
          type: "permission_request", requestId: "r1", toolCallId: "c1", title: "Run ls?", description: null,
          options: [{ optionId: "allow", name: "Yes", kind: "allow_once", description: "Run it this once" }, { optionId: "no", name: "No", kind: "reject_once", description: null }],
          outcome: { state: "pending" },
        }}
        sessionId="s1"
      />
      <ActivityRowView row={activityRow(call({ id: "e1", kind: "edit", title: "Edit bracket", locations: [{ path: "models/deeply/nested/bracket.step", line: null }] }))} onToggle={vi.fn()} open={false} sessionId="s1" />
      <SubagentRow part={{ type: "subagent", sessionId: "c1", name: "Docs checker", task: "confirm the README", state: "running", parts: [call({ id: "k1" })] }} sessionId="s1" />
    </TranscriptScopeContext.Provider>
    </TooltipProvider>,
  );

  // The ones that only appear once something is there: an attached image, the linked path, the
  // annotation list, the reference chip.
  const input = view.container.querySelector<HTMLInputElement>("[data-attach-input]")!;
  Object.defineProperty(input, "files", { configurable: true, value: [new File(["x"], "shot.png", { type: "image/png" })] });
  await act(async () => fireEvent.change(input));
  await waitFor(() => expect(screen.getByRole("button", { name: /Enlarge shot\.png/ })).toBeInTheDocument());
  await waitFor(() => expect(screen.getByRole("button", { name: "models/x.step#o1" })).toBeInTheDocument());
  await user.click(screen.getByRole("button", { name: "Edit 1 annotation" }));
  expect(screen.getByRole("button", { name: "Show annotation 1 on the model" })).toBeInTheDocument();
  expect(view.container.querySelector("[data-reference-chip] button")).not.toBeNull();

  const controls = screen.getAllByRole("button");
  expect(controls.length).toBeGreaterThan(15);
  expect(titled()).toEqual([]);
});

it("text the session shows in full elsewhere carries no native title either", () => {
  const state: SessionState = {
    ...initialSessionState("s1", "codex"),
    turns: [{ id: "t1", role: "user", startedAt: 0, parts: [{ type: "resource_link", uri: "attachment:///notes.txt", name: "notes.txt" }] }],
  } as never;
  render(
    <TooltipProvider>
    <TranscriptScopeContext.Provider value={scope}>
      <StatusLine active text="Running the build of every part in the assembly" />
      <Transcript onReconnect={vi.fn()} onRetry={vi.fn()} state={state} />
    </TranscriptScopeContext.Provider>
    </TooltipProvider>,
  );
  expect(screen.getByText("notes.txt")).toBeInTheDocument();
  expect([...document.querySelectorAll("[title]")].map((element) => element.outerHTML.slice(0, 120))).toEqual([]);
});

it("no control in the sidebar carries a native title, a row with changes included", async () => {
  const changed = { ...SESSION, gitMode: "none", pinned: false, changedFiles: 2, insertions: 9, deletions: 1 } as Session;
  useSettings.setState({ settings: defaultSettings(), ready: true });
  // One pinned, so its row in Pinned also draws its project's name.
  useSessions.setState({ sessions: [changed, { ...changed, id: "s2", title: "Hinge", pinned: true }], ready: true, activeId: "s1" });
  render(
    <TooltipProvider>
      <Sidebar />
    </TooltipProvider>,
  );
  expect(screen.getAllByRole("button", { name: /^Review changes: 2 files changed, 9 added, 1 removed/ })).toHaveLength(2);
  expect(screen.getByRole("button", { name: "Hinge" })).toBeInTheDocument();
  expect(titled()).toEqual([]);

  // The project's folder the header's title used to give is a hint on its name, open or not.
  const header = screen.getByRole("button", { name: "p", expanded: true });
  await userEvent.hover(within(header).getByText("p"));
  expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent("/p");
});

describe("Settings", () => {
  const agent = (installed: boolean) =>
    ({
      id: installed ? "claude-code" : "opencode",
      name: installed ? "Claude Code" : "OpenCode",
      description: "An agent",
      websiteUrl: "https://example.com",
      docsUrl: "https://example.com/docs",
      icon: null,
      installed,
      binaryPath: installed ? "/bin/claude" : null,
      version: installed ? "1.0.0" : null,
      auth: installed ? "authenticated" : "unknown",
      authMethods: [],
      capabilities: {},
      install: { macos: [], windows: [], linux: [] },
      launch: { command: "npx", args: [], env: {} },
      skillRoots: "native",
    }) as unknown as AgentStatus;

  beforeEach(() => {
    // Every value a page prints in a truncating line: a chosen path, a log, a skills root.
    useSettings.setState({ settings: { ...defaultSettings(), worktreeRoot: "/Users/me/worktrees" }, ready: true });
    useAgents.setState({ agents: [agent(true), agent(false)], ready: true, loadError: null });
    vi.mocked(window.textToCad.agents.list).mockResolvedValue([agent(true), agent(false)]);
    vi.mocked(window.textToCad.skills.info).mockResolvedValue({ root: "/Users/me/Library/skills/0.0.0", skills: [] });
    const status = { state: "missing", python: null, source: null, cadgenVersion: null, viewerBuilt: false, log: "/Users/me/cad-runtime.log", message: "No runtime" } as const;
    vi.mocked(window.textToCad.runtime.status).mockResolvedValue(status);
    useRuntime.setState({ status });
    // A project with a worktree that has uncommitted work: Delete is off, and says why.
    useProjects.setState({ projects: [{ id: "p", name: "p", path: "/p", createdAt: 0 }], activeId: "p" });
    vi.mocked(window.textToCad.git.worktrees).mockResolvedValue([
      { path: "/Users/me/worktrees/p/fillet", branch: "text-to-cad/fillet", lastUsedAt: null, openSessions: 0, dirty: true, locked: false },
    ]);
  });

  it.each(SETTINGS_SECTIONS)("no control or line on %s carries a native title", async (section) => {
    useUi.setState({ route: "settings", settingsSection: section });
    render(
      <TooltipProvider>
        <SettingsRoute />
      </TooltipProvider>,
    );
    await act(async () => {});
    if (section === "git") {
      const remove = await screen.findByRole("button", { name: "Delete" });
      expect(remove).toBeDisabled();
      expect(remove).toHaveAccessibleDescription(/uncommitted changes or ignored files/);
    }
    expect([...document.querySelectorAll("[title]")].map((element) => element.outerHTML.slice(0, 120))).toEqual([]);
  });

  it("nor does the agent drawer", async () => {
    render(
      <TooltipProvider>
        <AgentDrawer agent={agent(true)} onOpenChange={() => {}} open platform="macos" />
      </TooltipProvider>,
    );
    expect(await screen.findByText("/Users/me/Library/skills/0.0.0")).toBeInTheDocument();
    expect([...document.querySelectorAll("[title]")].map((element) => element.outerHTML.slice(0, 120))).toEqual([]);
  });
});

// Every `title` attribute on the page. An svg's own `<title>` child is not one, and one on an
// svg descendant is the icon's accessible name, not a tooltip.
const nativeTitles = () =>
  [...document.querySelectorAll("[title]")].filter((element) => !element.closest("svg")).map((element) => element.outerHTML.slice(0, 120));

describe("Explorer", () => {
  it("nor does the tab strip: a file tab's path is a hint on the tab", async () => {
    const file = { id: "f1", kind: "file", sessionId: "s1", projectId: "p", order: 0, root: null, panel: null, path: "models/deeply/nested/bracket.step" };
    const terminal = { id: "t1", kind: "terminal", sessionId: "s1", projectId: "p", order: 1, ptyId: null, cwd: null, readOnly: false };
    useExplorer.setState({ tabs: [file, terminal] as never, activeId: "f1", collapsed: false });
    render(<TooltipProvider><TabStrip /></TooltipProvider>);
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(nativeTitles()).toEqual([]);
    await userEvent.hover(screen.getAllByRole("tab")[0]!);
    expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent("models/deeply/nested/bracket.step");
  });

  it("nor does the review: branch, file rows, diff headers and a stale-read strip", async () => {
    const status: GitStatus = {
      isRepository: true, branch: "main", unborn: false, ahead: 0, behind: 0, insertions: 1, deletions: 0, workingFiles: 1,
      files: [{ path: "models/bracket.step", status: "modified", insertions: 1, deletions: 0, binary: false }],
    };
    const git = window.textToCad.git as unknown as { status: ReturnType<typeof vi.fn>; fileDiff: ReturnType<typeof vi.fn> };
    git.status.mockResolvedValueOnce(status).mockRejectedValueOnce(new Error("index.lock exists"));
    git.fileDiff.mockResolvedValue({ path: "models/bracket.step", before: "", after: "ISO-10303", binary: false, truncated: false });
    useSessions.setState({ sessions: [{ ...SESSION, cwd: "/p/worktree" }], ready: true });
    render(<TooltipProvider><ReviewTab project={{ id: "p", name: "p", path: "/p", createdAt: 0 }} scope="session" sessionId="s1" tabId="t1" /></TooltipProvider>);
    expect(await screen.findByText("main")).toBeInTheDocument();
    await screen.findAllByRole("button", { name: /bracket\.step/ });
    await act(async () => useExplorer.setState({ fsRevision: useExplorer.getState().fsRevision + 1 }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not refresh: index.lock exists");
    expect(nativeTitles()).toEqual([]);
  });
});
