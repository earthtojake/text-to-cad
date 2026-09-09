import type { GitChange } from '@emdash/core/runtimes/git/api';
import { describe, expect, it } from 'vitest';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import { buildChangesTree } from './changes-tree-utils';

describe('buildChangesTree', () => {
  it('renders portable workspace-relative change paths', () => {
    const change: GitChange = {
      path: portablePath('src/index.ts'),
      status: 'modified',
      additions: 2,
      deletions: 1,
    };

    const tree = buildChangesTree([change], '/repo');

    expect(tree.rootNodes.map((node) => node.path)).toEqual(['src']);
    expect(tree.rootNodes[0]?.children[0]?.path).toBe('src/index.ts');
    expect(tree.changeByPath.get('src/index.ts')).toBe(change);
    expect(tree.changeByPath.get('src/index.ts')?.path).toBe('src/index.ts');
  });

  it('keeps relative node paths addressable when no root path is provided', () => {
    const change: GitChange = {
      path: portablePath('src/index.ts'),
      status: 'modified',
      additions: 2,
      deletions: 1,
    };

    const tree = buildChangesTree([change]);
    const src = tree.rootNodes[0];
    const file = src?.children[0];
    const filePath = file?.path;

    expect(src?.path).toBe('src');
    expect(filePath).toBe('src/index.ts');
    expect(filePath ? tree.changeByPath.get(filePath) : undefined).toBe(change);
  });
});
