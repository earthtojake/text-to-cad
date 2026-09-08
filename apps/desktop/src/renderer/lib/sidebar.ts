/**
 * What the sidebar lists, as one pure function of the index and the filter
 * menu — plus the state glyph each row gets.
 *
 * A module rather than logic inside the components, for the same reason
 * `lib/panes.ts` and `lib/git-mode.ts` are: the answer has four inputs
 * (the sessions, the projects, the filters, the collapsed set) and five rules
 * on top of them, and a section that quietly listed a pinned thread twice, or
 * kept an empty project on screen when the toggle said not to, is a defect
 * nobody can see in a screenshot. Everything here is pure and unit-tested
 * (`tests/unit/renderer/sidebar.test.ts`); the components only draw it.
 */
import type {
  Project,
  Session,
  SessionStatus,
  SidebarSettings,
  SidebarSortBy,
} from "@shared/types";

/* -------------------------------------------------------------------------- */
/* The sections                                                                */
/* -------------------------------------------------------------------------- */

/**
 * A section of the sidebar. Exactly one of three kinds:
 *
 *   - `pinned`   the `Pinned` section, present only when something is in it;
 *   - `project`  one project's threads, with the project's own header;
 *   - `all`      the one flat list `Group by › None` produces.
 *
 * `project` is set only for the `project` kind, which is what makes the
 * header's `+`, its right-click menu and its collapse a project's business
 * and nothing else's.
 */
export type SidebarSection = {
  /** Stable across renders: the project's id, or the kind for the other two. */
  id: string;
  kind: "pinned" | "project" | "all";
  /** The header's text. */
  name: string;
  project: Project | null;
  sessions: Session[];
};

/**
 * The sidebar's list, in the order it is drawn: `Pinned` first when anything
 * is pinned, then the sections the grouping asks for.
 *
 * Five rules, and the tests are named after them:
 *
 *  1. **The filters come first.** `status` and `environment` decide which
 *     sessions exist at all; everything below sees only what survived.
 *  2. **A pinned thread lives in `Pinned` and nowhere else** — Claude Code's
 *     behaviour, and the only one that makes pinning mean anything: a row
 *     that stayed in its project as well would just be a duplicate.
 *  3. **`Group by › Project` keeps the project list's own order**, which is
 *     the order projects were added (`projects.list`). `None` is one list.
 *  4. **`Sort by` orders inside every section**, `Pinned` included.
 *  5. **`Show empty groups`** is about project headers only. A flat list has
 *     no header to keep, and `Pinned` is only there when it is not empty.
 */
export function sidebarSections(input: {
  sessions: readonly Session[];
  projects: readonly Project[];
  filters: SidebarSettings;
}): SidebarSection[] {
  const { filters } = input;
  const matching = input.sessions.filter(
    (session) => matchesStatus(session, filters) && matchesEnvironment(session, filters),
  );

  const sections: SidebarSection[] = [];

  const pinned = sort(
    matching.filter((session) => session.pinned),
    filters.sortBy,
  );
  if (pinned.length > 0) {
    sections.push({ id: "pinned", kind: "pinned", name: "Pinned", project: null, sessions: pinned });
  }

  const loose = matching.filter((session) => !session.pinned);

  if (filters.groupBy === "none") {
    sections.push({
      id: "all",
      kind: "all",
      name: "Sessions",
      project: null,
      sessions: sort(loose, filters.sortBy),
    });
    return sections;
  }

  for (const project of input.projects) {
    const sessions = sort(
      loose.filter((session) => session.projectId === project.id),
      filters.sortBy,
    );
    if (sessions.length === 0 && !filters.showEmptyGroups) {
      continue;
    }
    sections.push({ id: project.id, kind: "project", name: project.name, project, sessions });
  }

  return sections;
}

function matchesStatus(session: Session, filters: SidebarSettings): boolean {
  switch (filters.status) {
    case "active":
      return !session.archived;
    case "archived":
      return session.archived;
    case "all":
      return true;
  }
}

/**
 * `local` is both git modes that run in the project's own directory: whether
 * that directory happens to be a checkout is a fact about the project, not a
 * third environment (the same argument `GIT_MODE_LABELS` makes).
 */
function matchesEnvironment(session: Session, filters: SidebarSettings): boolean {
  switch (filters.environment) {
    case "all":
      return true;
    case "worktree":
      return session.gitMode === "worktree";
    case "local":
      return session.gitMode !== "worktree";
  }
}

/** A new array, always: the input is a store's own list. */
function sort(sessions: readonly Session[], by: SidebarSortBy): Session[] {
  const rows = [...sessions];
  switch (by) {
    case "activity":
      return rows.sort((a, b) => b.updatedAt - a.updatedAt || compareTitles(a, b));
    case "created":
      return rows.sort((a, b) => b.createdAt - a.createdAt || compareTitles(a, b));
    case "name":
      return rows.sort((a, b) => compareTitles(a, b));
  }
}

/**
 * Titles as a person reads them, and the id as the tiebreak so the order is
 * total: two threads can share a title, and a sort that left them in index
 * order would reshuffle the list every time the index came back over IPC.
 */
function compareTitles(a: Session, b: Session): number {
  const byTitle = a.title.localeCompare(b.title, undefined, { sensitivity: "base" });
  return byTitle !== 0 ? byTitle : a.id.localeCompare(b.id);
}

/* -------------------------------------------------------------------------- */
/* The state glyph                                                             */
/* -------------------------------------------------------------------------- */

/**
 * The leading glyph on a session row, from the index's status:
 *
 *   - `idle`        a hollow circle — nothing to say, and the row it is on is
 *                   the common case, so it must be the quietest mark;
 *   - `running`     a filled dot that pulses;
 *   - `waiting`     an amber triangle: the agent is blocked on the person,
 *                   which is the one state a sidebar exists to surface;
 *   - `error`       a red triangle;
 *   - `connecting`  a hollow circle with a spinner ring around it.
 *
 * `closed` is `idle`: an adapter that is not running is not a state the person
 * has to do anything about — the next prompt reconnects it (plan §5).
 */
export type SessionGlyph = "idle" | "running" | "waiting" | "error" | "connecting";

export function sessionGlyphFor(status: SessionStatus): SessionGlyph {
  switch (status) {
    case "running":
      return "running";
    case "waiting":
      return "waiting";
    case "error":
      return "error";
    case "connecting":
      return "connecting";
    case "idle":
    case "closed":
      return "idle";
  }
}

/** What the glyph's label says, for the tooltip and for the accessible name. */
export const SESSION_GLYPH_LABELS: Record<SessionGlyph, string> = {
  idle: "Idle",
  running: "Working",
  waiting: "Waiting for you",
  error: "Failed",
  connecting: "Connecting",
};
