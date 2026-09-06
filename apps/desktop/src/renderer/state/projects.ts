import { create } from "zustand";

import type { Project } from "@shared/types";

/**
 * The project list, mirrored from main. Every mutation is an IPC call; the
 * `projects.changed` event is what actually updates this store, so a change
 * made from the menu or another window lands here too.
 */
type ProjectsState = {
  projects: Project[];
  ready: boolean;
  /** The project the sidebar and the session pane are scoped to. */
  activeId: string | null;
  /** Project rows the user has collapsed. */
  collapsed: Set<string>;

  load: () => Promise<void>;
  /** Opens the native folder chooser. Resolves to null when cancelled. */
  add: () => Promise<Project | null>;
  remove: (id: string) => Promise<void>;
  rename: (id: string, name: string) => Promise<void>;
  setActive: (id: string | null) => void;
  toggleCollapsed: (id: string) => void;
  receive: (projects: Project[]) => void;
};

export const useProjects = create<ProjectsState>((set, get) => ({
  projects: [],
  ready: false,
  activeId: null,
  collapsed: new Set(),

  load: async () => {
    const projects = await window.hardcore.projects.list();
    set({ projects, ready: true, activeId: get().activeId ?? projects[0]?.id ?? null });
  },

  add: async () => {
    const project = await window.hardcore.projects.add();
    if (project) {
      set({ activeId: project.id });
    }
    return project;
  },

  remove: async (id) => {
    await window.hardcore.projects.remove({ id });
    if (get().activeId === id) {
      set({ activeId: null });
    }
  },

  rename: async (id, name) => {
    await window.hardcore.projects.rename({ id, name });
  },

  setActive: (activeId) => set({ activeId }),

  toggleCollapsed: (id) =>
    set((state) => {
      const collapsed = new Set(state.collapsed);
      if (!collapsed.delete(id)) {
        collapsed.add(id);
      }
      return { collapsed };
    }),

  receive: (projects) =>
    set((state) => ({
      projects,
      ready: true,
      // A removed project must not stay selected, and the first project added
      // to an empty app should be the one the session pane talks about.
      activeId:
        state.activeId && projects.some((project) => project.id === state.activeId)
          ? state.activeId
          : (projects[0]?.id ?? null),
    })),
}));

/** The active project object, or null. */
export function useActiveProject(): Project | null {
  return useProjects(
    (state) => state.projects.find((project) => project.id === state.activeId) ?? null,
  );
}
