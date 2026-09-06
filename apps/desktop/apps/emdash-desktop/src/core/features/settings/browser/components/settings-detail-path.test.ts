import { describe, expect, it } from 'vitest';
import { settingsDetailPathSchema } from '@core/features/settings/contributions/views';
import type { SettingsPageDetailContribution } from '@core/primitives/settings/api/page-contribution';
import { resolveDetailLevels } from './settings-detail-path';

const Noop = () => null;

function level(
  labels: Record<string, string | null>,
  child?: SettingsPageDetailContribution
): SettingsPageDetailContribution {
  return {
    component: Noop,
    breadcrumbLabel: (path) => labels[path.at(-1) ?? ''] ?? null,
    child,
  };
}

describe('settingsDetailPathSchema', () => {
  it('accepts a string array', () => {
    expect(settingsDetailPathSchema.parse(['a', 'b'])).toEqual(['a', 'b']);
  });

  it('coerces a legacy string to a one-element path', () => {
    expect(settingsDetailPathSchema.parse('legacy-id')).toEqual(['legacy-id']);
  });

  it('rejects non-string values', () => {
    expect(settingsDetailPathSchema.safeParse(42).success).toBe(false);
    expect(settingsDetailPathSchema.safeParse([42]).success).toBe(false);
  });
});

describe('resolveDetailLevels', () => {
  const chain = level({ m1: 'Machine One' }, level({ p1: 'Project One' }));

  it('resolves an empty path to no levels', () => {
    expect(resolveDetailLevels({ detail: chain }, [])).toEqual([]);
  });

  it('resolves a full two-level path', () => {
    const levels = resolveDetailLevels({ detail: chain }, ['m1', 'p1']);
    expect(levels.map((entry) => entry.label)).toEqual(['Machine One', 'Project One']);
    expect(levels.map((entry) => entry.path)).toEqual([['m1'], ['m1', 'p1']]);
  });

  it('passes ancestor segments to breadcrumbLabel', () => {
    const seen: string[][] = [];
    const spying: SettingsPageDetailContribution = {
      component: Noop,
      breadcrumbLabel: (path) => {
        seen.push([...path]);
        return 'ok';
      },
      child: {
        component: Noop,
        breadcrumbLabel: (path) => {
          seen.push([...path]);
          return 'ok';
        },
      },
    };
    resolveDetailLevels({ detail: spying }, ['a', 'b']);
    expect(seen).toEqual([['a'], ['a', 'b']]);
  });

  it('truncates at an unresolvable segment', () => {
    const levels = resolveDetailLevels({ detail: chain }, ['m1', 'missing']);
    expect(levels.map((entry) => entry.label)).toEqual(['Machine One']);
  });

  it('truncates when the first segment is unresolvable', () => {
    expect(resolveDetailLevels({ detail: chain }, ['missing', 'p1'])).toEqual([]);
  });

  it('truncates a path deeper than the declared chain', () => {
    const levels = resolveDetailLevels({ detail: chain }, ['m1', 'p1', 'too-deep']);
    expect(levels.map((entry) => entry.label)).toEqual(['Machine One', 'Project One']);
  });

  it('resolves nothing for a page without a detail contribution', () => {
    expect(resolveDetailLevels({ detail: undefined }, ['a'])).toEqual([]);
  });
});
