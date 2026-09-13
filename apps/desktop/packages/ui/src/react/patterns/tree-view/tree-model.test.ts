import { describe, expect, it } from 'vitest';
import { buildVisibleTreeRows, isChainExpanded, type TreeNode } from './tree-model';

interface FixtureNode {
  name: string;
}

const tree: TreeNode<FixtureNode>[] = [
  {
    id: 'src',
    data: { name: 'src' },
    children: [
      {
        id: 'src/app',
        data: { name: 'app' },
        children: [
          {
            id: 'src/app/index.ts',
            data: { name: 'index.ts' },
          },
        ],
      },
    ],
  },
  {
    id: 'README.md',
    data: { name: 'README.md' },
  },
];

describe('buildVisibleTreeRows', () => {
  it('flattens expanded branches', () => {
    const rows = buildVisibleTreeRows(tree, new Set(['src']));

    expect(rows.map((row) => row.node.id)).toEqual(['src', 'src/app', 'README.md']);
    expect(rows.map((row) => row.depth)).toEqual([0, 1, 0]);
  });

  it('hides descendants of collapsed branches', () => {
    const rows = buildVisibleTreeRows(tree, new Set());

    expect(rows.map((row) => row.node.id)).toEqual(['src', 'README.md']);
  });

  it('compacts single-branch chains', () => {
    const rows = buildVisibleTreeRows(tree, new Set(['src', 'src/app']), {
      compactChains: true,
    });

    expect(rows.map((row) => row.node.id)).toEqual(['src/app', 'src/app/index.ts', 'README.md']);
    expect(rows[0]?.chain.map((segment) => segment.id)).toEqual(['src', 'src/app']);
    expect(rows.map((row) => row.depth)).toEqual([0, 1, 0]);
  });
});

describe('isChainExpanded', () => {
  it('requires every compacted segment to be expanded', () => {
    const chain = [tree[0]!, tree[0]!.children![0]!];

    expect(isChainExpanded(chain, new Set(['src', 'src/app']))).toBe(true);
    expect(isChainExpanded(chain, new Set(['src']))).toBe(false);
  });
});
