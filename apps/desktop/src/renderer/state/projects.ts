import { create } from "zustand";

import { projectsFromSessions } from "@renderer/lib/projects";
import type { Project, Session } from "@shared/types";

/**
 * Directory descriptors derived from the session index, never saved projects.
 * `draft` is only the folder chosen for a session that has not been created yet;
 * it does not add a sidebar group and does not survive a relaunch.
 */
type ProjectsState = {
  projects: Project[];
  ready: boolean;
  activeId: string | null;
  draft: Project | null;
  /** Opens the native folder chooser without creating any persistent state. */
  add: () => Promise<Project | null>;
  setActive: (id: string | null) => void;
  selectDirectory: (project: Project) => void;
  derive: (sessions: readonly Session[]) => void;
};

export const useProjects = create<ProjectsState>((set, get) => ({
  projects: [],
  ready: false,
  activeId: null,
  draft: null,

  add: async () => {
    const project = await window.hardcore.projects.add();
    if (project) {
      get().selectDirectory(project);
    }
    return project;
  },

  selectDirectory: (project) => set({ activeId: project.id, draft: project }),

  setActive: (activeId) => set((state) => ({
    activeId,
    draft: state.draft?.id === activeId ? state.draft : null,
  })),

  derive: (sessions) => {
    const projects = projectsFromSessions(sessions);
    const activeIds = new Set(sessions.filter(session => !session.archived).map(session => session.projectId));
    const state = get();
    // session/create broadcasts a provisional connecting row before the agent
    // accepts it. Keep the draft through that phase so a failed connection can
    // remove its row without unmounting the composer and its error message.
    const established = sessions.some(session => !session.archived && session.projectId === state.draft?.id && session.acpSessionId);
    const draft = established ? null : state.draft;
    set({
      projects,
      ready: true,
      draft,
      activeId: state.activeId && (activeIds.has(state.activeId) || draft?.id === state.activeId)
        ? state.activeId
        : projects.find(project => activeIds.has(project.id))?.id ?? null,
    });
  },
}));

/** The selected session directory, including a folder chosen for its first draft. */
export function useActiveProject(): Project | null {
  return useProjects((state) =>
    state.draft?.id === state.activeId ? state.draft :
      state.projects.find((project) => project.id === state.activeId) ?? null,
  );
}
