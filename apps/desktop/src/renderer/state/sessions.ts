import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import type { Session } from "@shared/types";

/**
 * The session index — id, title, status, cwd. Not the transcripts: the agent
 * owns those and `session/load` replays them (plan §5).
 *
 * P1 fills in creation, resumption and the live status updates. Until then the
 * list is real but always empty, which is exactly what the sidebar's "No
 * sessions yet" state is for.
 */
type SessionsState = {
  sessions: Session[];
  ready: boolean;
  activeId: string | null;

  load: () => Promise<void>;
  setActive: (id: string | null) => void;
  receive: (sessions: Session[]) => void;
};

export const useSessions = create<SessionsState>((set) => ({
  sessions: [],
  ready: false,
  activeId: null,

  load: async () => {
    const sessions = await window.hardcore.sessions.list({});
    set({ sessions, ready: true });
  },

  setActive: (activeId) => set({ activeId }),

  receive: (sessions) => set({ sessions, ready: true }),
}));

/**
 * A project's sessions, newest first. `useShallow` because the selector builds
 * a fresh array every call, and zustand compares with Object.is — without it
 * this re-renders forever.
 */
export function useProjectSessions(projectId: string): Session[] {
  return useSessions(
    useShallow((state) => state.sessions.filter((session) => session.projectId === projectId)),
  );
}
