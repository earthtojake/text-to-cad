import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { Sidebar } from "@renderer/features/sidebar/Sidebar";
import { SESSION_GLYPH_LABELS, sessionGlyphFor, sidebarSections } from "@renderer/lib/sidebar";
import { useExplorer } from "@renderer/state/explorer";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import {
  SidebarSettingsSchema,
  defaultSettings,
  type Project,
  type Session,
  type Settings,
  type SessionStatus,
  type SidebarSettings,
} from "@shared/types";

const wrap = (ui: React.ReactNode) => render(<TooltipProvider>{ui}</TooltipProvider>);

const project = (id: string, name = id): Project => ({
  id,
  name,
  path: `/tmp/${id}`,
  createdAt: 0,
});

const session = (overrides: Partial<Session> & { id: string; title: string }): Session => ({
  projectId: "p1",
  titleSource: "prompt",
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
  pinned: false,
  sessionHead: null,
  turnHead: null,
  ...overrides,
});

const filters = (overrides: Partial<SidebarSettings> = {}): SidebarSettings =>
  SidebarSettingsSchema.parse(overrides);

/* -------------------------------------------------------------------------- */
/* The selector                                                                */
/* -------------------------------------------------------------------------- */

describe("sidebarSections", () => {
  const projects = [project("p1", "text-to-cad"), project("p2", "tom-cad")];

  it("puts one section per project, in the project list's own order", () => {
    const sections = sidebarSections({
      projects,
      filters: filters(),
      sessions: [
        session({ id: "a", title: "Alpha" }),
        session({ id: "b", title: "Beta", projectId: "p2" }),
      ],
    });
    expect(sections.map((section) => [section.kind, section.name])).toEqual([
      ["project", "text-to-cad"],
      ["project", "tom-cad"],
    ]);
    expect(sections[0]!.sessions.map((row) => row.id)).toEqual(["a"]);
    expect(sections[1]!.sessions.map((row) => row.id)).toEqual(["b"]);
  });

  it("lifts a pinned thread into Pinned and leaves it out of its project", () => {
    const sections = sidebarSections({
      projects,
      filters: filters(),
      sessions: [
        session({ id: "a", title: "Alpha", pinned: true }),
        session({ id: "b", title: "Beta" }),
      ],
    });
    expect(sections[0]!.kind).toBe("pinned");
    expect(sections[0]!.sessions.map((row) => row.id)).toEqual(["a"]);
    // Not in both places: a pinned row that stayed under its project would
    // just be a duplicate of itself.
    const inProject = sections.find((s) => s.id === "p1")!.sessions.map((row) => row.id);
    expect(inProject).toEqual(["b"]);
  });

  it("has no Pinned section when nothing is pinned", () => {
    const sections = sidebarSections({
      projects,
      filters: filters(),
      sessions: [session({ id: "a", title: "Alpha" })],
    });
    expect(sections.some((s) => s.kind === "pinned")).toBe(false);
  });

  it("filters by status", () => {
    const sessions = [
      session({ id: "live", title: "Live" }),
      session({ id: "old", title: "Old", archived: true }),
    ];
    const ids = (status: SidebarSettings["status"]) =>
      sidebarSections({ projects, filters: filters({ status }), sessions })
        .flatMap((section) => section.sessions)
        .map((row) => row.id);
    expect(ids("active")).toEqual(["live"]);
    expect(ids("archived")).toEqual(["old"]);
    expect(ids("all").sort()).toEqual(["live", "old"]);
  });

  it("filters by environment, with both local git modes counting as local", () => {
    const sessions = [
      session({ id: "none", title: "Plain", gitMode: "none" }),
      session({ id: "checkout", title: "Checkout", gitMode: "checkout" }),
      session({ id: "tree", title: "Tree", gitMode: "worktree" }),
    ];
    const ids = (environment: SidebarSettings["environment"]) =>
      sidebarSections({ projects, filters: filters({ environment }), sessions })
        .flatMap((section) => section.sessions)
        .map((row) => row.id)
        .sort();
    expect(ids("all")).toEqual(["checkout", "none", "tree"]);
    expect(ids("local")).toEqual(["checkout", "none"]);
    expect(ids("worktree")).toEqual(["tree"]);
  });

  it("collapses the projects into one list when the grouping says none", () => {
    const sections = sidebarSections({
      projects,
      filters: filters({ groupBy: "none" }),
      sessions: [
        session({ id: "a", title: "Alpha", updatedAt: 1 }),
        session({ id: "b", title: "Beta", projectId: "p2", updatedAt: 2 }),
      ],
    });
    expect(sections).toHaveLength(1);
    expect(sections[0]!.kind).toBe("all");
    expect(sections[0]!.project).toBeNull();
    expect(sections[0]!.sessions.map((row) => row.id)).toEqual(["b", "a"]);
  });

  it("sorts inside every section, Pinned included", () => {
    const sessions = [
      session({ id: "a", title: "Zulu", createdAt: 3, updatedAt: 1 }),
      session({ id: "b", title: "Alpha", createdAt: 1, updatedAt: 3 }),
      session({ id: "c", title: "Mike", createdAt: 2, updatedAt: 2, pinned: true }),
      session({ id: "d", title: "Bravo", createdAt: 4, updatedAt: 0, pinned: true }),
    ];
    const order = (sortBy: SidebarSettings["sortBy"], id: string) =>
      sidebarSections({ projects, filters: filters({ sortBy }), sessions })
        .find((section) => section.id === id)!
        .sessions.map((row) => row.id);
    expect(order("activity", "p1")).toEqual(["b", "a"]);
    expect(order("created", "p1")).toEqual(["a", "b"]);
    expect(order("name", "p1")).toEqual(["b", "a"]);
    expect(order("activity", "pinned")).toEqual(["c", "d"]);
    expect(order("name", "pinned")).toEqual(["d", "c"]);
  });

  it("never shows a group without matching unpinned sessions, including old settings", () => {
    const sessions = [session({ id: "a", title: "Alpha" })];
    expect(sidebarSections({ projects, filters: SidebarSettingsSchema.parse({ showEmptyGroups: true }), sessions })
      .map(section => section.id)).toEqual(["p1"]);
    expect(sidebarSections({ projects, filters: filters(), sessions: [{ ...sessions[0]!, pinned: true }] })
      .map(section => section.id)).toEqual(["pinned"]);
    expect(sidebarSections({ projects, filters: filters(), sessions: [{ ...sessions[0]!, archived: true }] }))
      .toEqual([]);
  });

});

/* -------------------------------------------------------------------------- */
/* The state glyph                                                             */
/* -------------------------------------------------------------------------- */

describe("sessionGlyphFor", () => {
  it("maps every status a session row can have", () => {
    const expected: Record<SessionStatus, string> = {
      idle: "idle",
      // An adapter that is not running is nothing for the person to do:
      // the next prompt reconnects it.
      closed: "idle",
      running: "running",
      waiting: "waiting",
      error: "error",
      connecting: "connecting",
    };
    for (const [status, glyph] of Object.entries(expected)) {
      expect(sessionGlyphFor(status as SessionStatus), status).toBe(glyph);
    }
  });

  it("labels each glyph, so the mark is not the only way to read it", () => {
    expect(SESSION_GLYPH_LABELS.waiting).toBe("Waiting for you");
    expect(Object.values(SESSION_GLYPH_LABELS).every((label) => label.length > 0)).toBe(true);
  });
});

/* -------------------------------------------------------------------------- */
/* The panel                                                                   */
/* -------------------------------------------------------------------------- */

describe("Sidebar", () => {
  beforeEach(() => {
    useProjects.setState({ projects: [], ready: true, activeId: null, draft: null });
    useSessions.setState({ sessions: [], ready: true, activeId: null });
    useSettings.setState({ settings: defaultSettings(), ready: true });
    useUi.setState({
      route: "app",
      settingsSection: "general",
      commandPaletteOpen: false,
      commandPaletteQuery: "",
    });
  });

  const withProject = () => {
    useProjects.setState({
      projects: [project("p1", "text-to-cad")],
      ready: true,
      activeId: "p1",
    });
  };

  /**
   * The chooser is `Open folder…` on the project chip's menu, and with no
   * projects it is the main area's button — the panel says it is empty and
   * does not repeat that button.
   */
  it("says it is empty when there are no projects, without a second chooser", () => {
    wrap(<Sidebar />);
    expect(screen.getByText("No sessions yet")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open folder…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add project" })).not.toBeInTheDocument();

    withProject();
    wrap(<Sidebar />);
    expect(screen.queryByRole("button", { name: "Add project" })).not.toBeInTheDocument();
  });

  it("says the filters hide everything, and clears them, instead of offering a folder", async () => {
    const user = userEvent.setup();
    useProjects.setState({ projects: [project("p1", "text-to-cad")], ready: true, activeId: "p1", draft: null });
    useSessions.setState({ sessions: [session({ id: "s1", title: "Bracket" })], ready: true, activeId: null });
    useSettings.setState({ settings: { ...defaultSettings(), sidebar: filters({ status: "archived" }) }, ready: true });
    vi.mocked(window.textToCad.settings.set).mockImplementationOnce(async (patch) => ({ ...useSettings.getState().settings!, ...(patch as Partial<Settings>) }));
    wrap(<Sidebar />);

    expect(screen.getByText("No sessions match these filters")).toBeInTheDocument();
    expect(screen.queryByText("No sessions yet")).toBeNull();
    expect(screen.queryByRole("button", { name: "Open folder…" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(useSettings.getState().settings?.sidebar).toMatchObject({ status: "active", environment: "all" });
    expect(screen.getByText("Bracket")).toBeInTheDocument();
  });

  it("shows a just-picked folder as a pending group, not as no sessions", () => {
    const draft = project("d1", "gearbox");
    useProjects.setState({ projects: [], ready: true, activeId: "d1", draft });
    wrap(<Sidebar />);

    expect(screen.getByText("gearbox — new session")).toBeInTheDocument();
    expect(screen.queryByText("No sessions yet")).toBeNull();
  });

  it("starts a thread from `New`, not from `New session`", () => {
    wrap(<Sidebar />);
    expect(screen.getByRole("button", { name: "New" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New session" })).not.toBeInTheDocument();
  });

  it("does not show an empty directory group", () => {
    withProject();
    wrap(<Sidebar />);
    expect(screen.queryByRole("button", { name: "text-to-cad", expanded: true })).not.toBeInTheDocument();
    // What shows instead is the panel's own empty card, not a group's.
    expect(screen.getByText("No sessions yet").closest("[data-sidebar-empty]")).not.toBeNull();
  });

  it("lists a project's threads flat, newest first, and hides archived ones", () => {
    withProject();
    useSessions.setState({
      sessions: [
        session({ id: "s1", title: "Session 1", updatedAt: 1 }),
        session({ id: "s2", title: "Session 2", updatedAt: 2 }),
        session({ id: "gone", title: "Archived one", archived: true, updatedAt: 100 }),
      ],
      ready: true,
      activeId: "s2",
    });
    wrap(<Sidebar />);
    expect(screen.getAllByText(/^Session \d$/).map((node) => node.textContent)).toEqual([
      "Session 2",
      "Session 1",
    ]);
    expect(screen.queryByText("Archived one")).not.toBeInTheDocument();
  });

  it("draws the state glyph and git's, so neither hides the other", () => {
    withProject();
    useSessions.setState({
      sessions: [
        session({ id: "a", title: "Busy", status: "running" }),
        session({ id: "b", title: "Asked", status: "waiting" }),
        session({ id: "c", title: "Broken", status: "error" }),
        session({ id: "d", title: "Tree", gitMode: "worktree", branch: "text-to-cad/x" }),
        session({ id: "e", title: "Branch", gitMode: "checkout", branch: "main" }),
      ],
      ready: true,
      activeId: null,
    });
    wrap(<Sidebar />);
    // The glyph is drawn only; its word is the title button's description.
    expect(screen.getByRole("button", { name: "Busy" })).toHaveAccessibleDescription("Working");
    expect(screen.getByRole("button", { name: "Asked" })).toHaveAccessibleDescription("Waiting for you");
    expect(screen.getByRole("button", { name: "Broken" })).toHaveAccessibleDescription("Failed");
    expect(screen.getByLabelText(/^Worktree/)).toBeInTheDocument();
    expect(screen.getByLabelText("main")).toBeInTheDocument();
  });

  it("marks a waiting thread as needing the person, not as a warning", () => {
    withProject();
    useSessions.setState({
      sessions: [session({ id: "b", title: "Asked", status: "waiting" })],
      ready: true,
      activeId: null,
    });
    wrap(<Sidebar />);
    const glyph = document.querySelector('[data-session-glyph="waiting"] svg')!;
    expect(glyph.getAttribute("class")).toContain("text-info");
    expect(glyph.getAttribute("class")).not.toContain("warning");
  });

  it("marks the session on screen with aria-current, and only it", () => {
    withProject();
    useSessions.setState({ sessions: [session({ id: "s1", title: "One" }), session({ id: "s2", title: "Two" })], ready: true, activeId: "s2" });
    wrap(<Sidebar />);
    expect(screen.getByRole("button", { name: "Two" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("button", { name: "One" })).not.toHaveAttribute("aria-current");
  });

  it("rings the row for keyboard focus, not the title button inside it", () => {
    withProject();
    useSessions.setState({ sessions: [session({ id: "s1", title: "One" })], ready: true, activeId: null });
    wrap(<Sidebar />);
    const row = document.querySelector('[data-session-row="s1"]')!;
    const title = screen.getByRole("button", { name: "One" });
    expect(row.getAttribute("class")).toContain("has-[[data-session-row-title]:focus-visible]:ring-2");
    expect(title.getAttribute("class")).not.toContain("ring");
    expect(title.getAttribute("class")).toContain("focus-visible:outline-none");
  });

  it("shows what a thread changed and opens that thread's review from it", async () => {
    const user = userEvent.setup();
    withProject();
    useSessions.setState({
      sessions: [
        session({ id: "s1", title: "Changed", changedFiles: 2, insertions: 9, deletions: 1 }),
        session({ id: "s2", title: "Untouched" }),
      ],
      ready: true,
      activeId: "s2",
    });
    const open = vi.fn(() => null);
    // The strip is still s2's: nothing may open in it.
    useExplorer.setState({ sessionId: "s2", ready: true, tabs: [], open } as never);
    wrap(<Sidebar />);
    const pill = screen.getByRole("button", { name: /Review changes: 2 files changed/ });
    expect(pill).toHaveTextContent("+9−1");
    // The row counts what the agent reported; Review counts git. The name says so.
    expect(pill).toHaveAccessibleName(/Edits the agent reported this session; Review shows the working tree/);
    expect(pill).not.toHaveAttribute("title");
    expect(document.querySelectorAll("[data-session-changes]")).toHaveLength(1);

    await user.click(pill);
    expect(useSessions.getState().activeId).toBe("s1");
    expect(open).not.toHaveBeenCalled();
    // The bridge binds the explorer to the selected session; then it opens.
    useExplorer.setState({ sessionId: "s1", ready: true } as never);
    expect(open).toHaveBeenCalledWith("review", { scope: "session" });
  });

  it("drops a pending review when the selection moves on before the explorer binds", async () => {
    const user = userEvent.setup();
    withProject();
    useSessions.setState({
      sessions: [
        session({ id: "a", title: "Alpha", changedFiles: 1, insertions: 2, deletions: 0 }),
        session({ id: "b", title: "Beta" }),
      ],
      ready: true,
      activeId: "b",
    });
    const open = vi.fn(() => null);
    useExplorer.setState({ sessionId: "b", ready: true, tabs: [], open } as never);
    wrap(<Sidebar />);
    // A's badge, then row B, then row A — all before A's explorer binds.
    await user.click(screen.getByRole("button", { name: /Review changes/ }));
    await user.click(screen.getByRole("button", { name: "Beta" }));
    await user.click(screen.getByRole("button", { name: "Alpha" }));
    useExplorer.setState({ sessionId: "a", ready: true } as never);
    expect(open).not.toHaveBeenCalled();
  });

  it("brings an open review forward instead of opening a second one", async () => {
    const user = userEvent.setup();
    withProject();
    useSessions.setState({
      sessions: [session({ id: "s1", title: "Changed", changedFiles: 1, insertions: 3, deletions: 0 })],
      ready: true,
      activeId: "s1",
    });
    const open = vi.fn(() => null);
    const setActive = vi.fn();
    const update = vi.fn();
    const show = vi.fn();
    useExplorer.setState({
      sessionId: "s1",
      ready: true,
      tabs: [{ id: "r1", kind: "review", scope: "all" }],
      open,
      setActive,
      update,
      show,
    } as never);
    wrap(<Sidebar />);
    const pill = screen.getByRole("button", { name: /Review changes/ });
    // A zero side is not drawn: no red `−0`.
    expect(pill).toHaveTextContent(/^\+3$/);
    await user.click(pill);
    expect(open).not.toHaveBeenCalled();
    expect(update).toHaveBeenCalledWith("r1", { scope: "session" });
    expect(setActive).toHaveBeenCalledWith("r1");
  });

  it("collapses a project into its header and writes it to the settings", async () => {
    const user = userEvent.setup();
    const set = vi.fn(async (patch: Record<string, unknown>) => ({
      ...defaultSettings(),
      ...patch,
    }));
    (window.textToCad.settings as unknown as Record<string, unknown>).set = set;
    withProject();
    useSessions.setState({
      sessions: [session({ id: "s1", title: "Session 1" })],
      ready: true,
      activeId: null,
    });
    wrap(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "text-to-cad", expanded: true }));
    expect(set).toHaveBeenCalledWith(
      expect.objectContaining({ sidebar: expect.objectContaining({ collapsedProjects: ["p1"] }) }),
    );
    // Optimistic, so the row is gone before the round trip lands.
    expect(screen.queryByText("Session 1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "text-to-cad", expanded: false })).toBeInTheDocument();
  });

  it("a collapsed project's header shows its strongest hidden state; an expanded one shows none", () => {
    withProject();
    const collapsedSettings = { ...defaultSettings(), sidebar: filters({ collapsedProjects: ["p1"] }) };
    useSettings.setState({ settings: collapsedSettings, ready: true });
    useSessions.setState({
      sessions: [
        session({ id: "s1", title: "Running one", status: "running" }),
        session({ id: "s2", title: "Needs you", status: "waiting" }),
        session({ id: "s3", title: "Quiet", status: "idle" }),
      ],
      ready: true,
      activeId: null,
    });
    const view = wrap(<Sidebar />);
    expect(screen.queryByText("Needs you")).not.toBeInTheDocument();
    const header = view.container.querySelector("[data-sidebar-section-header]")!;
    expect(within(header as HTMLElement).getByRole("img", { name: "1 thread waiting for you" })).toBeInTheDocument();
    expect(header.querySelector('[data-session-glyph="waiting"]')).not.toBeNull();

    // Nothing waiting: the running one is what is left to say.
    act(() => useSessions.setState({ sessions: [session({ id: "s1", title: "Running one", status: "running" })] }));
    expect(within(header as HTMLElement).getByRole("img", { name: "1 thread working" })).toBeInTheDocument();

    // Expanded, the rows say it themselves and the header says nothing.
    act(() => useSettings.setState({ settings: { ...defaultSettings(), sidebar: filters() } }));
    expect(screen.getByText("Running one")).toBeInTheDocument();
    expect(header.querySelector("[data-sidebar-section-state]")).toBeNull();
  });

  it("pins from the row's menu, and the row moves to Pinned", async () => {
    const user = userEvent.setup();
    const setPinned = vi.fn(async () => undefined);
    (window.textToCad.sessions as unknown as Record<string, unknown>).setPinned = setPinned;
    withProject();
    useSessions.setState({
      sessions: [session({ id: "s1", title: "Keeper" })],
      ready: true,
      activeId: null,
    });
    const view = wrap(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "Keeper actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Pin" }));
    expect(setPinned).toHaveBeenCalledWith({ id: "s1", pinned: true });

    // The index is what moves the row — `sessions.changed` in the app, and
    // the store's own list here.
    useSessions.setState({ sessions: [session({ id: "s1", title: "Keeper", pinned: true })] });
    view.rerender(
      <TooltipProvider>
        <Sidebar />
      </TooltipProvider>,
    );
    expect(screen.getByText("Pinned")).toBeInTheDocument();
    expect(screen.getAllByText("Keeper")).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "text-to-cad", expanded: true })).not.toBeInTheDocument();
  });

  /**
   * Search and the filters act on the whole list, so they are the panel's
   * header and not each project's. A project header carries `+` and nothing
   * else: the glyph that opened the palette with one project's name typed is
   * gone, and so is the per-header copy of a menu whose settings were always
   * global.
   */
  it("keeps search and the filters in the panel's header, not on a project's", async () => {
    const user = userEvent.setup();
    withProject();
    wrap(<Sidebar />);

    expect(screen.getByRole("button", { name: "Search" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Search text-to-cad" })).not.toBeInTheDocument();
    // One filter menu in the panel, whatever the projects are.
    expect(screen.getAllByRole("button", { name: "Filters" })).toHaveLength(1);

    // And it is the global menu: the settings, with no `Project…` submenu.
    await user.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByRole("menuitem", { name: /^Status/ })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Project…" })).not.toBeInTheDocument();
  });

  it("opens the palette from the panel's search glyph, with nothing typed", async () => {
    const user = userEvent.setup();
    withProject();
    wrap(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(useUi.getState().commandPaletteOpen).toBe(true);
    expect(useUi.getState().commandPaletteQuery).toBe("");
  });

  it("starts a thread in the project the `+` belongs to", async () => {
    const user = userEvent.setup();
    useProjects.setState({
      projects: [project("p1", "text-to-cad"), project("p2", "tom-cad")],
      ready: true,
      activeId: "p1",
    });
    useSessions.setState({
      sessions: [session({ id: "s1", title: "Keeper" }), session({ id: "s2", title: "Other", projectId: "p2" })],
      ready: true,
      activeId: "s1",
    });
    wrap(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "New session in tom-cad" }));
    expect(useProjects.getState().activeId).toBe("p2");
    expect(useSessions.getState().activeId).toBeNull();
  });
});
