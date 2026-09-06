import { create } from "zustand";
import { useShallow } from "zustand/react/shallow";

import type { GitMode, Session } from "@shared/types";

import { useAgents } from "./agents";
import { useSettings } from "./settings";

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
  const installed = useAgents.getState().agents.filter((agent) => agent.installed);
  const preferred = useSettings.getState().settings?.defaultAgentId;
  if (preferred && installed.some((agent) => agent.id === preferred)) {
    return preferred;
  }
  return installed[0]?.id ?? null;
}

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
