import { create } from "zustand";

import { useProjects } from "./projects";
import { useSessions } from "./sessions";

/**
 * Back and forward, over the one thing the session pane can be showing.
 *
 * A location is a project and either one of its sessions or none — the
 * new-session screen. That is the whole of the top level: the explorer's tabs
 * are not in here (a tab strip has its own row and its own order, and a back
 * button that closed a file would be a lie), and Settings is not either — it
 * replaces the shell and comes back to whatever was under it.
 *
 * Entries are recorded by watching the selection rather than by every caller
 * remembering to push one. There are half a dozen doors into "show me this
 * thread" — the sidebar's rows, the palette, `Cmd+N`, the app menu, an agent
 * starting a session, Settings' `New chat in this worktree` — and a push at
 * each is a push someone will forget. `sync` pushes only when the location
 * actually changed, which is also why back and forward push nothing: they
 * *set* the selection to the entry they moved to, so by the time `sync` runs
 * the location already equals the cursor's entry.
 *
 * A deleted session's entry is skipped rather than removed, in both
 * directions, so the stack keeps its shape while the person walks past it.
 */

export type Location = {
  projectId: string;
  /** Null is that project's new-session screen. */
  sessionId: string | null;
};

/** What still exists — an entry pointing outside it is skipped. */
export type Live = {
  projectIds: readonly string[];
  sessionIds: readonly string[];
};

type HistoryState = {
  entries: Location[];
  /** Which entry is on screen; -1 before the first one is recorded. */
  index: number;
  /**
   * Record the selection if it moved. Truncates anything ahead of the cursor,
   * the way a browser does: navigating on from a page you went back to drops
   * the forward stack.
   */
  sync: () => void;
  back: () => void;
  forward: () => void;
};

/** Whether an entry still points at something that exists. */
export function isLive(entry: Location, live: Live): boolean {
  if (!live.projectIds.includes(entry.projectId)) {
    return false;
  }
  return entry.sessionId === null || live.sessionIds.includes(entry.sessionId);
}

/**
 * The nearest live entry in `step`'s direction, or -1 — which is also the
 * answer to "is there anything to go to", and so to whether the button is
 * muted. The buttons are never hidden, only muted, so both ends of the stack
 * have to be a state and not an absence.
 */
export function findLive(
  entries: readonly Location[],
  from: number,
  step: -1 | 1,
  live: Live,
): number {
  for (let at = from + step; at >= 0 && at < entries.length; at += step) {
    const entry = entries[at];
    if (entry && isLive(entry, live)) {
      return at;
    }
  }
  return -1;
}

const same = (a: Location, b: Location) => a.projectId === b.projectId && a.sessionId === b.sessionId;

/** The location the stores are showing, or null with no project bound. */
function locationNow(): Location | null {
  const projectId = useProjects.getState().activeId;
  if (!projectId) {
    return null;
  }
  const { activeId, sessions } = useSessions.getState();
  // A session belonging to another project is a selection caught in flight —
  // the two stores are set one after the other — and the project decides.
  const session = sessions.find((candidate) => candidate.id === activeId);
  return { projectId, sessionId: session && session.projectId === projectId ? session.id : null };
}

function liveNow(): Live {
  return {
    projectIds: useProjects.getState().projects.map((project) => project.id),
    sessionIds: useSessions.getState().sessions.map((session) => session.id),
  };
}

/** Put a location on screen, through the stores' own setters. */
function show(entry: Location): void {
  useProjects.getState().setActive(entry.projectId);
  useSessions.getState().setActive(entry.sessionId);
}

export const useHistory = create<HistoryState>((set, get) => ({
  entries: [],
  index: -1,

  sync: () => {
    const location = locationNow();
    if (!location) {
      return;
    }
    const { entries, index } = get();
    const at = entries[index];
    if (at && same(at, location)) {
      return;
    }
    const kept = entries.slice(0, index + 1);
    kept.push(location);
    set({ entries: kept, index: kept.length - 1 });
  },

  back: () => {
    const { entries, index } = get();
    const target = findLive(entries, index, -1, liveNow());
    const entry = entries[target];
    if (entry) {
      set({ index: target });
      show(entry);
    }
  },

  forward: () => {
    const { entries, index } = get();
    const target = findLive(entries, index, 1, liveNow());
    const entry = entries[target];
    if (entry) {
      set({ index: target });
      show(entry);
    }
  },
}));

/**
 * Watch the two stores a location is made of and record what they land on.
 *
 * A microtask rather than the subscription itself: `useSessions.select` sets
 * the project and then the session, and a push per `set` would file the
 * intermediate state — that project's new-session screen — as a place the
 * person had been. Reading once the call stack is done sees only where they
 * ended up.
 */
export function attachHistory(): () => void {
  let queued = false;
  const record = () => {
    if (queued) {
      return;
    }
    queued = true;
    queueMicrotask(() => {
      queued = false;
      useHistory.getState().sync();
    });
  };
  const offProjects = useProjects.subscribe(record);
  const offSessions = useSessions.subscribe(record);
  record();
  return () => {
    offProjects();
    offSessions();
  };
}

/** Whether each button has somewhere to go, for the two places they are drawn. */
export function useHistoryReach(): { back: boolean; forward: boolean } {
  const entries = useHistory((state) => state.entries);
  const index = useHistory((state) => state.index);
  // The project and session lists are subscribed to as well: an entry whose
  // session has been deleted stops being somewhere to go back to, and the
  // button has to mute itself when that was the last one.
  const projects = useProjects((state) => state.projects);
  const sessions = useSessions((state) => state.sessions);
  const live: Live = {
    projectIds: projects.map((project) => project.id),
    sessionIds: sessions.map((session) => session.id),
  };
  return {
    back: findLive(entries, index, -1, live) >= 0,
    forward: findLive(entries, index, 1, live) >= 0,
  };
}
