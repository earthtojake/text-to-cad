import { createListView, createTextMatcher } from '@emdash/ui/react/patterns';
import type { SshConfig } from '@core/primitives/ssh/api';

export const MACHINES_SECTION_RECENT = 'Recently used';
export const MACHINES_SECTION_OTHER = 'Other';

/**
 * The list-view state layer for the Machines settings page: sync source read
 * straight from the MobX machines store (so the pipeline re-derives on store
 * changes), name-sorted, with immediate search over name, host, and username
 * and Recently-used/Other sections driven by connection state.
 */
export function createMachinesListView(options: {
  getMachines: () => readonly SshConfig[];
  isRecentlyUsed: (machine: SshConfig) => boolean;
}) {
  return createListView({
    getItemId: (machine: SshConfig) => machine.id,
    source: {
      kind: 'sync',
      items: () =>
        options
          .getMachines()
          .slice()
          .sort((left, right) => left.name.localeCompare(right.name)),
    },
    search: {
      kind: 'sync',
      predicate: createTextMatcher((machine: SshConfig) => [
        machine.name,
        machine.host,
        machine.username,
      ]),
    },
    sections: {
      by: (machine) =>
        options.isRecentlyUsed(machine) ? MACHINES_SECTION_RECENT : MACHINES_SECTION_OTHER,
      order: [MACHINES_SECTION_RECENT, MACHINES_SECTION_OTHER],
    },
  });
}

export type MachinesListViewModel = ReturnType<typeof createMachinesListView>;
