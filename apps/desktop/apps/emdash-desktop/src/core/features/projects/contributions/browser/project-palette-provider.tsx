import { Command } from 'cmdk';
import { FolderOpen } from 'lucide-react';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';
import {
  matchPaletteText,
  type PaletteContext,
  type PaletteProviderDef,
  type PaletteProviderMatch,
  type PaletteProviderQuery,
  type PaletteProviderRenderProps,
} from '@core/primitives/palette/api';
import type { SearchItem } from '@core/primitives/search/api';
import {
  getIdleProjectPaletteEntities,
  searchProjectPaletteEntities,
} from './project-palette-source';

const PROJECT_PALETTE_ITEM_CLASS =
  'flex cursor-pointer items-center gap-2.5 text-foreground-muted aria-selected:text-foreground rounded-md px-2 py-2 text-sm aria-selected:bg-background-2';

interface ProjectPaletteProviderDependencies {
  readonly search?: (input: PaletteProviderQuery) => Promise<readonly SearchItem[]>;
  readonly idle?: (context: PaletteContext) => readonly SearchItem[];
}

function ProjectPaletteRow({
  match,
  value,
  onSelect,
}: PaletteProviderRenderProps<PaletteProviderMatch>) {
  const { navigate } = useNavigate();
  const handleSelect = () => {
    onSelect();
    navigate(projectViewDef({ projectId: match.id }));
  };

  return (
    <Command.Item value={value} onSelect={handleSelect} className={PROJECT_PALETTE_ITEM_CLASS}>
      <FolderOpen size={14} className="shrink-0 text-foreground/40" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate">{match.title}</span>
        {match.subtitle && (
          <span className="truncate text-xs text-foreground/40">{match.subtitle}</span>
        )}
      </span>
    </Command.Item>
  );
}

export function createProjectPaletteProvider({
  search = searchProjectPaletteEntities,
  idle = getIdleProjectPaletteEntities,
}: ProjectPaletteProviderDependencies = {}): PaletteProviderDef<'projects'> {
  return {
    kind: 'projects',
    keyword: '@projects',
    minQueryLength: 1,
    idle: (context) =>
      idle(context).map((item) => ({
        id: item.id,
        title: item.title,
        section: 'Projects',
        relevance: { band: 'fuzzy', score: 0 },
      })),
    search: async ({ query, context }) =>
      (await search({ query, context })).flatMap((item) => {
        if (item.kind !== 'project') return [];
        const relevance = matchPaletteText(query, {
          primary: [item.title],
          secondary: [item.subtitle],
        });
        if (!relevance) return [];
        return [
          {
            id: item.id,
            title: item.title,
            subtitle: item.subtitle || undefined,
            relevance: {
              ...relevance,
              contextAffinity: item.id === context.projectId ? 1 : 0,
            },
          },
        ];
      }),
    render: ProjectPaletteRow,
  };
}

export const projectPaletteProviderDefs = [createProjectPaletteProvider()] as const;
