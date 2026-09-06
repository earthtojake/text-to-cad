import { describe, expect, it } from 'vitest';
import {
  ancestorPathsFor,
  buildFileTreeNodes,
  buildFlatFileRows,
  canMoveNode,
  creationTargetPath,
  dedupeDescendantPaths,
  isExpandableFileTreeNode,
  isOpenableFileTreeNode,
  normalizeFileTreePath,
  resolveDropTargetDir,
  selectionRange,
  sortFileNodes,
  type ChildrenById,
  type FileTreeNode,
} from './file-tree-utils';

const src: FileTreeNode = {
  id: 'src',
  path: 'src',
  name: 'src',
  parentId: null,
  parentPath: '',
  depth: 0,
  type: 'directory',
};

const components: FileTreeNode = {
  id: 'src/components',
  path: 'src/components',
  name: 'components',
  parentId: 'src',
  parentPath: 'src',
  depth: 1,
  type: 'directory',
};

const app: FileTreeNode = {
  id: 'src/app.tsx',
  path: 'src/app.tsx',
  name: 'app.tsx',
  parentId: 'src',
  parentPath: 'src',
  depth: 1,
  type: 'file',
};

const button: FileTreeNode = {
  id: 'src/components/button.tsx',
  path: 'src/components/button.tsx',
  name: 'button.tsx',
  parentId: 'src/components',
  parentPath: 'src/components',
  depth: 2,
  type: 'file',
};

const readme: FileTreeNode = {
  id: 'README.md',
  path: 'README.md',
  name: 'README.md',
  parentId: null,
  parentPath: '',
  depth: 0,
  type: 'file',
};

const childrenById: ChildrenById = new Map([
  [null, [readme, src]],
  ['src', [app, components]],
  ['src/components', [button]],
]);

describe('file-tree utils', () => {
  it('sorts directories before files and compares names naturally', () => {
    const nodes = sortFileNodes([readme, app, components, src]);

    expect(nodes.map((node) => node.name)).toEqual(['components', 'src', 'app.tsx', 'README.md']);
  });

  it('builds generic tree nodes from a flat children map', () => {
    const nodes = buildFileTreeNodes([readme, src], childrenById);

    expect(nodes.map((node) => node.id)).toEqual(['src', 'README.md']);
    expect(nodes[0]?.children?.map((node) => node.id)).toEqual(['src/components', 'src/app.tsx']);
  });

  it('builds flat file rows with directory labels', () => {
    const rows = buildFlatFileRows([readme, src], childrenById);

    expect(rows.map((row) => [row.node.path, row.directory])).toEqual([
      ['src/components/button.tsx', 'src/components'],
      ['src/app.tsx', 'src'],
      ['README.md', ''],
    ]);
  });

  it('resolves creation targets from selection', () => {
    expect(creationTargetPath(null, '')).toBe('');
    expect(creationTargetPath(src, '')).toBe('src');
    expect(creationTargetPath(app, '')).toBe('src');
  });

  it('normalizes platform-specific separators without using host path APIs', () => {
    expect(normalizeFileTreePath('src\\components//button.tsx/')).toBe('src/components/button.tsx');
  });

  it('treats symlinks according to their target kind', () => {
    const directoryLink: FileTreeNode = {
      ...components,
      id: 'linked-components',
      path: 'linked-components',
      name: 'linked-components',
      parentId: null,
      parentPath: '',
      depth: 0,
      type: 'symlink',
      symlink: true,
      symlinkTargetKind: 'directory',
    };
    const fileLink: FileTreeNode = {
      ...readme,
      id: 'README-link.md',
      path: 'README-link.md',
      name: 'README-link.md',
      type: 'symlink',
      symlink: true,
      symlinkTargetKind: 'file',
    };

    expect(isExpandableFileTreeNode(directoryLink)).toBe(true);
    expect(isOpenableFileTreeNode(directoryLink)).toBe(false);
    expect(isExpandableFileTreeNode(fileLink)).toBe(false);
    expect(isOpenableFileTreeNode(fileLink)).toBe(true);
  });

  it('resolves drop targets for directories, files, and root space', () => {
    const nodesByPath = new Map(
      [src, components, app, button, readme].map((node) => [node.path, node])
    );

    expect(resolveDropTargetDir(components, nodesByPath, '')).toEqual({
      targetDir: components,
      targetDirPath: 'src/components',
    });
    expect(resolveDropTargetDir(button, nodesByPath, '')).toEqual({
      targetDir: components,
      targetDirPath: 'src/components',
    });
    expect(resolveDropTargetDir(null, nodesByPath, '')).toEqual({
      targetDir: null,
      targetDirPath: '',
    });
  });

  it('lists ancestor directories outermost first so compacted chains can expand', () => {
    expect(ancestorPathsFor('src/components/button.tsx')).toEqual(['src', 'src/components']);
    expect(ancestorPathsFor('src')).toEqual([]);
    expect(ancestorPathsFor('repo/src/app', 'repo')).toEqual(['repo/src']);
  });

  it('guards invalid moves', () => {
    expect(canMoveNode('src/app.tsx', 'src')).toBe(false);
    expect(canMoveNode('src', 'src/components')).toBe(false);
    expect(canMoveNode('src', 'src')).toBe(false);
    expect(canMoveNode('src/app.tsx', '')).toBe(true);
    expect(canMoveNode('src/components/button.tsx', 'src')).toBe(true);
  });

  it('selects ranges over visible path order', () => {
    const visiblePaths = ['src', 'src/components', 'src/components/button.tsx', 'src/app.tsx'];

    expect(selectionRange(visiblePaths, 'src/components', 'src/app.tsx')).toEqual([
      'src/components',
      'src/components/button.tsx',
      'src/app.tsx',
    ]);
    expect(selectionRange(visiblePaths, null, 'src/app.tsx')).toEqual(['src/app.tsx']);
    expect(selectionRange(visiblePaths, 'missing', 'src/app.tsx')).toEqual(['src/app.tsx']);
  });

  it('dedupes descendants when dragging nested selections', () => {
    expect(
      dedupeDescendantPaths(['src/components/button.tsx', 'README.md', 'src', 'src/components'])
    ).toEqual(['src', 'README.md']);
  });
});
