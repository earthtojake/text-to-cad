import {
  workspaceChromeMemento,
  type WorkspaceChromeState,
} from '@core/features/projects/contributions/mementos';
import { defineChromeStore } from '@core/primitives/chrome-stores/api';
import type { ChromeStore } from '@core/primitives/chrome-stores/browser';

type WorkspaceChromeEphemeral = Record<string, never>;

type ZenState = WorkspaceChromeState['zen'];

/**
 * Workspace chrome command store (spec §Chrome command stores): the
 * `projects.workspace-chrome` memento document mutated only through named
 * commands, one instance per project subject. Zen mode is plain data inside
 * the document — `enterZenMode` snapshots the fields it overrides into
 * `zen.restore` and `exitZenMode` applies that snapshot — so zen persists
 * across restarts with a working restore.
 */
export const workspaceChromeStore = defineChromeStore({
  memento: workspaceChromeMemento,
  ephemeral: {} as WorkspaceChromeEphemeral,
  commands: {
    toggleLeftSidebar: ({ state }) => ({
      state: {
        ...state,
        leftSidebarOpen: !state.leftSidebarOpen,
        // Stale-restore guard: an explicit change while zen is active wins
        // over the snapshot, so exit keeps the user's value instead of
        // resurrecting the pre-zen one.
        zen: state.zen.active ? dropFromRestore(state.zen, 'leftSidebarOpen') : state.zen,
      },
    }),
    enterZenMode: ({ state }) => {
      if (state.zen.active) return;
      return {
        state: {
          ...state,
          leftSidebarOpen: false,
          zen: { active: true, restore: { leftSidebarOpen: state.leftSidebarOpen } },
        },
      };
    },
    exitZenMode: ({ state }) => {
      if (!state.zen.active) return;
      return {
        state: {
          ...state,
          leftSidebarOpen: state.zen.restore.leftSidebarOpen ?? state.leftSidebarOpen,
          zen: { active: false, restore: {} },
        },
      };
    },
  },
});

function dropFromRestore(zen: ZenState, field: keyof ZenState['restore']): ZenState {
  const restore = { ...zen.restore };
  delete restore[field];
  return { ...zen, restore };
}

export type WorkspaceChromeStore = ChromeStore<
  WorkspaceChromeState,
  WorkspaceChromeEphemeral,
  (typeof workspaceChromeStore)['commands']
>;
