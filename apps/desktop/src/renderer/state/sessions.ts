import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import { useProjects } from "./projects";
import type { Session } from "@shared/types";

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
  remove: (id: string) => Promise<void>;
  receive: (sessions: Session[]) => void;
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
        state.activeId && sessions.some((session) => session.id === state.activeId)
          ? state.activeId
          : null,
    })),
}));

/**
 * A project's unarchived sessions, newest first. `useShallow` because the
 * selector builds a fresh array every call, and zustand compares with
 * Object.is — without it this re-renders forever.
 */
export function useProjectSessions(projectId: string): Session[] {
  return useSessions(
    useShallow((state) =>
      state.sessions
        .filter((session) => session.projectId === projectId && !session.archived)
        .sort((a, b) => b.updatedAt - a.updatedAt),
    ),
  );
}

/** The active session's index row, or null in the new-session state. */
export function useActiveSession(): Session | null {
  return useSessions(
    (state) => state.sessions.find((session) => session.id === state.activeId) ?? null,
  );
}
