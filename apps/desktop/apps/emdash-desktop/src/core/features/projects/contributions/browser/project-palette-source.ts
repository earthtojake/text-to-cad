import type { ProjectStore } from '@core/features/projects/api/browser/stores/project';
import {
  asAvailableProject,
  getProjectManagerStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { getSearchClient, type SearchClient } from '@core/features/search/api/client';
import type { PaletteContext, PaletteProviderQuery } from '@core/primitives/palette/api';
import type { SearchItem } from '@core/primitives/search/api';

const IDLE_PROJECT_LIMIT = 5;
const PROJECT_SOURCE_LIMIT = 50;

type GetProjectSearchClient = () => Promise<Pick<SearchClient, 'searchPaletteEntities'>>;

export async function searchProjectPaletteEntities(
  { query, context }: PaletteProviderQuery,
  getClient: GetProjectSearchClient = getSearchClient
): Promise<SearchItem[]> {
  const client = await getClient();
  return client.searchPaletteEntities({
    kind: 'project',
    query,
    context,
    limit: PROJECT_SOURCE_LIMIT,
  });
}

export function getIdleProjectPaletteEntities(
  context: PaletteContext,
  projectStores?: Iterable<ProjectStore>
): SearchItem[] {
  if (context.taskId) return [];

  const matches: SearchItem[] = [];
  const stores = projectStores ?? getProjectManagerStore().projects.values();
  for (const projectStore of stores) {
    const projectContext = asAvailableProject(projectStore);
    if (!projectContext || projectContext.project.id === context.projectId) continue;
    matches.push({
      kind: 'project',
      id: projectContext.project.id,
      projectId: null,
      taskId: null,
      title: projectStore.name ?? projectContext.project.id,
      subtitle: '',
      score: 0,
    });
    if (matches.length === IDLE_PROJECT_LIMIT) break;
  }
  return matches;
}
