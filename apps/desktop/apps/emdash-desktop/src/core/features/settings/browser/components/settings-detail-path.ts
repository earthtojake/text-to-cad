import type {
  SettingsPageContribution,
  SettingsPageDetailContribution,
} from '@core/primitives/settings/api/page-contribution';

export type ResolvedDetailLevel = {
  contribution: SettingsPageDetailContribution;
  /** The path prefix down to and including this level. */
  path: string[];
  label: string;
};

/**
 * Walks the page's declared detail chain alongside the path segments and
 * returns the resolved levels for the longest valid prefix. A prefix stops
 * being valid when the chain has no level declared for it or its
 * `breadcrumbLabel` resolves to null.
 */
export function resolveDetailLevels(
  page: Pick<SettingsPageContribution, 'detail'>,
  path: readonly string[]
): ResolvedDetailLevel[] {
  const levels: ResolvedDetailLevel[] = [];
  let contribution = page.detail;
  for (let depth = 0; depth < path.length; depth++) {
    if (!contribution) break;
    const prefix = path.slice(0, depth + 1);
    const label = contribution.breadcrumbLabel(prefix);
    if (label === null) break;
    levels.push({ contribution, path: prefix, label });
    contribution = contribution.child;
  }
  return levels;
}
