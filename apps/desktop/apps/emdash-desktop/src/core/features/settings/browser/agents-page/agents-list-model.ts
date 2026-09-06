import {
  createListView,
  createTextMatcher,
  type ExternalListSource,
} from '@emdash/ui/react/patterns';
import type { AgentPayload } from '@core/primitives/agents/api';

export const AGENTS_SECTION_INSTALLED = 'Installed';
export const AGENTS_SECTION_RECOMMENDED = 'Recommended';
export const AGENTS_SECTION_NOT_INSTALLED = 'Not installed';

const AGENTS_SECTION_ORDER = [
  AGENTS_SECTION_INSTALLED,
  AGENTS_SECTION_RECOMMENDED,
  AGENTS_SECTION_NOT_INSTALLED,
];

const RECOMMENDED_IDS = new Set(['claude', 'codex', 'pi']);

/** The slice of an agent payload the list model reads; tests build just this. */
export type AgentListItem = Pick<AgentPayload, 'id' | 'name' | 'status'>;

export function agentSectionLabel(agent: AgentListItem): string {
  if (agent.status === 'available') return AGENTS_SECTION_INSTALLED;
  return RECOMMENDED_IDS.has(agent.id) ? AGENTS_SECTION_RECOMMENDED : AGENTS_SECTION_NOT_INSTALLED;
}

/**
 * The list-view state layer for the CLI agents list: an externally owned source
 * (the component bridges its query via `useQueryListSource`) whose items the
 * model name-sorts, with immediate search over the agent name and the three
 * fixed Installed / Recommended / Not installed sections (empty sections are
 * dropped by the grouping pipeline).
 */
export function createAgentsListView<T extends AgentListItem>(source: ExternalListSource<T>) {
  return createListView({
    getItemId: (agent: T) => agent.id,
    source: {
      ...source,
      items: () =>
        source
          .items()
          .slice()
          .sort((left, right) => left.name.localeCompare(right.name)),
    },
    search: {
      kind: 'sync',
      predicate: createTextMatcher((agent: T) => [agent.name]),
    },
    sections: {
      by: agentSectionLabel,
      order: AGENTS_SECTION_ORDER,
    },
  });
}
