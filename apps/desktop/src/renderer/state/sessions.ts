import { useMemo } from "react";
import { create } from "zustand";

import { sidebarSections, type SidebarSection } from "@renderer/lib/sidebar";
import type { GitMode, Session } from "@shared/types";

import { useAgents } from "./agents";
import { useProjects } from "./projects";
import { useSettings, useSidebarSettings } from "./settings";

/**
 * The session index — id, title, status, cwd, the files-changed counters.
 * Not the transcripts: the agent owns those and `session/load` replays them
 * (plan §5); `state/acp.ts` holds the live state of the ones that are open.
 *
 * `activeId === null` is the new-session state for the active project. Every
 * mutation is an IPC call and the `sessions.changed` event that follows is
 * what updates the list, so a rename from the header and one from the
 * sidebar's menu land in the same place.
 */
type SessionsState = {
  sessions: Session[];
  ready: boolean;
  activeId: string | null;

  load: () => Promise<void>;
  setActive: (id: string | null) => void;
  /** Select a session and make its project the active one. */
  select: (id: string) => void;
  rename: (id: string, title: string) => Promise<void>;
  archive: (id: string, archived: boolean) => Promise<void>;
  /** Move the row into the sidebar's `Pinned` section, or back to its project. */
  setPinned: (id: string, pinned: boolean) => Promise<void>;
  remove: (id: string) => Promise<void>;
  receive: (sessions: Session[]) => void;
  /**
   * Start a thread and select it (plan §9).
   *
   * The working directory is main's to decide: this passes the mode, not a
   * path, and main resolves the worktree. `cwd` is the one exception —
   * Settings' `New chat in this worktree` names a directory that already
   * exists, and main checks it belongs to the project.
   */
  start: (input: {
    projectId: string;
    agentId?: string;
    gitMode?: GitMode;
    cwd?: string;
    name?: string;
  }) => Promise<Session>;
};

export const useSessions = create<SessionsState>((set, get) => ({
  sessions: [],
  ready: false,
  activeId: null,

  load: async () => {
    const sessions = await window.hardcore.sessions.list({});
    set({ sessions, ready: true });
  },

  setActive: (activeId) => set({ activeId }),

  select: (id) => {
    const session = get().sessions.find((candidate) => candidate.id === id);
    if (session && useProjects.getState().activeId !== session.projectId) {
      useProjects.getState().setActive(session.projectId);
    }
    set({ activeId: id });
  },

  rename: async (id, title) => {
    const trimmed = title.trim();
    if (!trimmed) {
      return;
    }
    // Optimistic: the header's inline edit should not flash the old title
    // back while the round trip completes. `sessions.changed` corrects it.
    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.id === id ? { ...session, title: trimmed } : session,
      ),
    }));
    await window.hardcore.sessions.rename({ id, title: trimmed });
  },

  archive: async (id, archived) => {
    await window.hardcore.sessions.archive({ id, archived });
    if (archived && get().activeId === id) {
      set({ activeId: null });
    }
  },

  setPinned: async (id, pinned) => {
    await window.hardcore.sessions.setPinned({ id, pinned });
  },

  remove: async (id) => {
    await window.hardcore.sessions.delete({ id });
    if (get().activeId === id) {
      set({ activeId: null });
    }
  },

  receive: (sessions) =>
    set((state) => ({
      sessions,
      ready: true,
      // A deleted session must not stay selected.
      activeId:
        state.activeId &&
        sessions.some((session) => session.id === state.activeId)
          ? state.activeId
          : null,
    })),

  start: async (input) => {
    const agentId = input.agentId ?? defaultAgentId();
    if (!agentId) {
      throw new Error("no agent is installed; add one from Settings › Agents");
    }
    const session = await window.hardcore.sessions.create({
      projectId: input.projectId,
      agentId,
      ...(input.gitMode ? { gitMode: input.gitMode } : {}),
      ...(input.cwd ? { cwd: input.cwd } : {}),
      ...(input.name ? { name: input.name } : {}),
    });
    set({ activeId: session.id });
    return session;
  },
}));

/**
 * Which agent a session gets when the caller does not say: the one Settings
 * names, and otherwise the first installed one.
 *
 * A default that pointed at an agent the person has since uninstalled would
 * fail at `session/new` with the adapter's own words, so the setting is only
 * honoured while the detector still finds it.
 */
function defaultAgentId(): string | null {
  const installed = useAgents
    .getState()
    .agents.filter((agent) => agent.installed);
  const preferred = useSettings.getState().settings?.defaultAgentId;
  if (preferred && installed.some((agent) => agent.id === preferred)) {
    return preferred;
  }
  return installed[0]?.id ?? null;
}

/**
 * The sidebar's sections — `Pinned`, then whatever the grouping asks for
 * (`lib/sidebar.ts`).
 *
 * `useMemo` over the three stores' own values rather than a zustand selector:
 * the sections are fresh objects on every call, so no equality zustand can
 * apply to the *result* is ever true and a selector re-renders forever (it
 * did). The three inputs, on the other hand, are stable references — a store
 * replaces its list when it changes and not otherwise — so memoising on them
 * recomputes exactly when one of them moves.
 */
export function useSidebarSections(): SidebarSection[] {
  const sessions = useSessions((state) => state.sessions);
  const projects = useProjects((state) => state.projects);
  const filters = useSidebarSettings();
  return useMemo(
    () => sidebarSections({ sessions, projects, filters }),
    [sessions, projects, filters],
  );
}

/** The active session's index row, or null in the new-session state. */
export function useActiveSession(): Session | null {
  return useSessions(
    (state) =>
      state.sessions.find((session) => session.id === state.activeId) ?? null,
  );
}
