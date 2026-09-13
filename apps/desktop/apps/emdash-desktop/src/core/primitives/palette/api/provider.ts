import type { ComponentType } from 'react';

export type PaletteProviderKind = 'commands' | 'tasks' | 'conversations' | 'files' | 'projects';

export type PaletteProviderKeyword = `@${string}`;

export interface PaletteContext {
  readonly projectId?: string;
  readonly taskId?: string;
  readonly workspaceId?: string;
}

export type PaletteMatchBand = 'exact' | 'prefix' | 'substring' | 'fuzzy' | 'secondary';

export interface PaletteRelevance {
  readonly band: PaletteMatchBand;
  readonly score: number;
  readonly contextAffinity?: number;
  readonly recency?: number;
}

export interface PaletteProviderMatch {
  readonly id: string;
  readonly title: string;
  readonly subtitle?: string;
  readonly section?: string;
  readonly relevance: PaletteRelevance;
}

export interface PaletteProviderQuery {
  readonly query: string;
  readonly context: PaletteContext;
}

export interface PaletteProviderRenderProps<TMatch extends PaletteProviderMatch> {
  readonly match: TMatch;
  readonly value: string;
  readonly onSelect: () => void;
}

export interface PaletteProviderDef<
  TKind extends PaletteProviderKind = PaletteProviderKind,
  TMatch extends PaletteProviderMatch = PaletteProviderMatch,
> {
  readonly kind: TKind;
  readonly keyword: PaletteProviderKeyword;
  readonly minQueryLength: number;
  readonly idle?: (context: PaletteContext) => readonly TMatch[] | Promise<readonly TMatch[]>;
  readonly search: (input: PaletteProviderQuery) => readonly TMatch[] | Promise<readonly TMatch[]>;
  readonly render: ComponentType<PaletteProviderRenderProps<TMatch>>;
}
