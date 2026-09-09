import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TooltipProvider } from "@hardcore/ui/primitives/tooltip";
import { Sidebar } from "@renderer/features/sidebar/Sidebar";
import { SESSION_GLYPH_LABELS, sessionGlyphFor, sidebarSections } from "@renderer/lib/sidebar";
import { useProjects } from "@renderer/state/projects";
import { useSessions } from "@renderer/state/sessions";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import {
  SidebarSettingsSchema,
  defaultSettings,
  type Project,
  type Session,
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
  turnStartedAt: null,
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

  it("keeps or drops a project with nothing in it, as the toggle says", () => {
    const sessions = [session({ id: "a", title: "Alpha" })];
    expect(
      sidebarSections({ projects, filters: filters({ showEmptyGroups: true }), sessions }).map(
        (section) => section.id,
      ),
    ).toEqual(["p1", "p2"]);
    expect(
      sidebarSections({ projects, filters: filters({ showEmptyGroups: false }), sessions }).map(
        (section) => section.id,
      ),
    ).toEqual(["p1"]);
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
    useProjects.setState({ projects: [], ready: true, activeId: null });
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
   * The chooser is `Open folder…` on the project chip's menu now, so the
   * panel has no `Add project` row — except in this one state, which has no
   * chip to open it from.
   */
  it("offers a way in when there are no projects, and no Add project row otherwise", () => {
    wrap(<Sidebar />);
    expect(screen.getByText("No projects yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open folder…" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add project" })).not.toBeInTheDocument();

    withProject();
    wrap(<Sidebar />);
    expect(screen.queryByRole("button", { name: "Add project" })).not.toBeInTheDocument();
  });

  it("starts a thread from `New`, not from `New chat`", () => {
    wrap(<Sidebar />);
    expect(screen.getByRole("button", { name: "New" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New chat" })).not.toBeInTheDocument();
  });

  it("gives a project a section header with an empty state under it", () => {
    withProject();
    wrap(<Sidebar />);
    expect(screen.getByRole("button", { name: "Collapse text-to-cad" })).toBeInTheDocument();
    expect(screen.getByText("No sessions yet")).toBeInTheDocument();
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
        session({ id: "d", title: "Tree", gitMode: "worktree", branch: "hardcore/x" }),
        session({ id: "e", title: "Branch", gitMode: "checkout", branch: "main" }),
      ],
      ready: true,
      activeId: null,
    });
    wrap(<Sidebar />);
    expect(screen.getByLabelText("Working")).toBeInTheDocument();
    expect(screen.getByLabelText("Waiting for you")).toBeInTheDocument();
    expect(screen.getByLabelText("Failed")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Worktree/)).toBeInTheDocument();
    expect(screen.getByLabelText("main")).toBeInTheDocument();
  });

  it("collapses a project into its header and writes it to the settings", async () => {
    const user = userEvent.setup();
    const set = vi.fn(async (patch: Record<string, unknown>) => ({
      ...defaultSettings(),
      ...patch,
    }));
    (window.hardcore.settings as unknown as Record<string, unknown>).set = set;
    withProject();
    useSessions.setState({
      sessions: [session({ id: "s1", title: "Session 1" })],
      ready: true,
      activeId: null,
    });
    wrap(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "Collapse text-to-cad" }));
    expect(set).toHaveBeenCalledWith(
      expect.objectContaining({ sidebar: expect.objectContaining({ collapsedProjects: ["p1"] }) }),
    );
    // Optimistic, so the row is gone before the round trip lands.
    expect(screen.queryByText("Session 1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Expand text-to-cad" })).toBeInTheDocument();
  });

  it("pins from the row's menu, and the row moves to Pinned", async () => {
    const user = userEvent.setup();
    const setPinned = vi.fn(async () => undefined);
    (window.hardcore.sessions as unknown as Record<string, unknown>).setPinned = setPinned;
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
    expect(screen.getByText("No sessions yet")).toBeInTheDocument();
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
      sessions: [session({ id: "s1", title: "Keeper" })],
      ready: true,
      activeId: "s1",
    });
    wrap(<Sidebar />);
    await user.click(screen.getByRole("button", { name: "New chat in tom-cad" }));
    expect(useProjects.getState().activeId).toBe("p2");
    expect(useSessions.getState().activeId).toBeNull();
  });
});
