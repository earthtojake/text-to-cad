import type { Meta, StoryObj } from '@storybook/react-vite';
import {
  CheckSquareIcon,
  CopyIcon,
  FilePenIcon,
  SquareArrowRightIcon,
  SquareDotIcon,
  SquareMinusIcon,
  SquarePlusIcon,
  SquareXIcon,
  Trash2Icon,
} from 'lucide-react';
import * as React from 'react';
import { Button } from '../../primitives/button';
import {
  FileTree,
  type FileTreeHandle,
  type FileTreeProps,
  type FileTreeRowState,
} from './file-tree';
import {
  canMoveNode,
  joinFileTreePath,
  normalizeFileTreePath,
  type ChildrenById,
  type FileTreeNode,
} from './file-tree-utils';

const meta: Meta<typeof FileTree> = {
  title: 'Components/FileTree',
  component: FileTree,
  parameters: { layout: 'padded' },
};
export default meta;

type Story = StoryObj<typeof FileTree>;

const baseNodes: FileTreeNode[] = [
  directory('src'),
  directory('src/components'),
  file('src/components/button.tsx'),
  file('src/components/file-tree.tsx'),
  directory('src/features'),
  directory('src/features/source-control'),
  file('src/features/source-control/changes-panel.tsx'),
  file('src/main.tsx'),
  directory('packages'),
  directory('packages/ui'),
  file('packages/ui/package.json'),
  symlink('linked-src', 'directory'),
  file('linked-src/index.ts'),
  symlink('docs-link.md', 'file'),
  file('README.md'),
  file('pnpm-lock.yaml'),
];

export const Interactive: Story = {
  render: () => (
    <StoryFrame>
      <MockFileTree initialNodes={baseNodes} />
    </StoryFrame>
  ),
};

export const DragToMove: Story = {
  render: () => (
    <StoryFrame note="Drag files or folders onto directories. Invalid moves are rejected by the mock dnd spec.">
      <MockFileTree initialNodes={baseNodes} enableDnd />
    </StoryFrame>
  ),
};

export const MultiSelect: Story = {
  render: () => (
    <StoryFrame note="Use Cmd/Ctrl-click and Shift-click to select multiple rows. Dragging a selected row moves the selection.">
      <MockFileTree initialNodes={baseNodes} enableDnd />
    </StoryFrame>
  ),
};

export const RenameAndSymlinks: Story = {
  render: () => (
    <StoryFrame note="Use the context menu to rename rows. linked-src is an expandable directory symlink; docs-link.md is file-like.">
      <MockFileTree initialNodes={baseNodes} />
    </StoryFrame>
  ),
};

export const CustomHeader: Story = {
  render: () => (
    <StoryFrame>
      <MockFileTree
        initialNodes={baseNodes}
        renderHeader={(context) => (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              borderBottom: '1px solid var(--em-border)',
              padding: 8,
            }}
          >
            <strong style={{ flex: 1, minWidth: 0, fontSize: 13 }}>
              Creating in {context.targetPath || 'root'}
            </strong>
            <Button size="xs" variant="secondary" onClick={() => context.startDraft('file')}>
              Add file
            </Button>
            <Button size="xs" variant="secondary" onClick={() => context.startDraft('directory')}>
              Add folder
            </Button>
          </div>
        )}
      />
    </StoryFrame>
  ),
};

export const RefDrivenHeader: Story = {
  render: () => (
    <StoryFrame>
      <RefDrivenHeaderStory />
    </StoryFrame>
  ),
};

export const OpenedAndSelected: Story = {
  render: () => (
    <StoryFrame>
      <MockFileTree
        initialNodes={baseNodes}
        initialSelectedPath="src/components/file-tree.tsx"
        initialOpenedPaths={new Set(['src/main.tsx', 'src/components/file-tree.tsx'])}
      />
    </StoryFrame>
  ),
};

export const Loading: Story = {
  args: {
    rootNodes: [],
    childrenById: new Map(),
    isLoading: true,
  },
  render: (args) => (
    <StoryFrame>
      <FileTree {...args} />
    </StoryFrame>
  ),
};

export const Error: Story = {
  args: {
    rootNodes: [],
    childrenById: new Map(),
    error: 'Unable to load this folder.',
  },
  render: (args) => (
    <StoryFrame>
      <FileTree {...args} />
    </StoryFrame>
  ),
};

export const Empty: Story = {
  args: {
    rootNodes: [],
    childrenById: new Map(),
  },
  render: (args) => (
    <StoryFrame>
      <FileTree {...args} />
    </StoryFrame>
  ),
};

export const LargeTree: Story = {
  render: () => (
    <StoryFrame height="34rem">
      <MockFileTree initialNodes={largeTreeNodes()} compactChains />
    </StoryFrame>
  ),
};

export const GitChangesTree: Story = {
  render: () => (
    <StoryFrame height="24rem">
      <MockGitChanges mode="tree" />
    </StoryFrame>
  ),
};

export const GitChangesList: Story = {
  render: () => (
    <StoryFrame height="24rem">
      <MockGitChanges mode="flat" />
    </StoryFrame>
  ),
};

function MockFileTree({
  initialNodes,
  initialSelectedPath = null,
  initialOpenedPaths,
  enableDnd = false,
  compactChains = false,
  renderHeader,
}: {
  initialNodes: readonly FileTreeNode[];
  initialSelectedPath?: string | null;
  initialOpenedPaths?: ReadonlySet<string>;
  enableDnd?: boolean;
  compactChains?: boolean;
  renderHeader?: FileTreeProps['renderHeader'];
}) {
  const [nodes, setNodes] = React.useState(() => cloneNodes(initialNodes));
  const { rootNodes, childrenById } = React.useMemo(() => deriveTree(nodes), [nodes]);
  const [expandedPaths, setExpandedPaths] = React.useState<ReadonlySet<string>>(
    () => new Set(['src', 'src/components', 'src/features', 'packages', 'packages/ui'])
  );
  const [selectedPath, setSelectedPath] = React.useState<string | null>(initialSelectedPath);
  const [selectedPaths, setSelectedPaths] = React.useState<ReadonlySet<string>>(() =>
    initialSelectedPath ? new Set([initialSelectedPath]) : new Set()
  );
  const [openedPaths, setOpenedPaths] = React.useState<ReadonlySet<string>>(
    () => initialOpenedPaths ?? new Set()
  );
  const [renamePath, setRenamePath] = React.useState<string | null>(null);
  const [lastAction, setLastAction] = React.useState('Open, create, move, or use a context menu.');

  return (
    <div
      style={{
        display: 'grid',
        height: '100%',
        minHeight: 0,
        gap: 8,
        gridTemplateRows: 'minmax(0, 1fr) auto',
      }}
    >
      <FileTree
        rootNodes={rootNodes}
        childrenById={childrenById}
        expandedPaths={expandedPaths}
        selectedPath={selectedPath}
        selectedPaths={selectedPaths}
        openedPaths={openedPaths}
        renamePath={renamePath}
        compactChains={compactChains}
        renderHeader={renderHeader}
        onToggleExpand={(node, expanded) => {
          setExpandedPaths((current) => togglePath(current, node.path, expanded));
        }}
        onCollapseAll={() => setExpandedPaths(new Set())}
        onExpandAll={(paths) => setExpandedPaths(new Set(paths))}
        onSelect={(node) => setSelectedPath(node?.path ?? null)}
        onSelectionChange={(paths, anchorPath) => {
          setSelectedPaths(new Set(paths));
          setSelectedPath(anchorPath);
        }}
        onOpenFile={(node, options) => {
          setOpenedPaths((current) => new Set(current).add(node.path));
          setLastAction(`${options.preview ? 'Previewed' : 'Opened'} ${node.path}`);
        }}
        onCreateFile={(parentPath, name) => {
          setNodes((current) => addNode(current, parentPath, name, 'file'));
          setLastAction(`Created file ${joinFileTreePath(parentPath, name)}`);
        }}
        onCreateDirectory={(parentPath, name) => {
          setNodes((current) => addNode(current, parentPath, name, 'directory'));
          setExpandedPaths((current) => new Set(current).add(joinFileTreePath(parentPath, name)));
          setLastAction(`Created folder ${joinFileTreePath(parentPath, name)}`);
        }}
        onRenameSubmit={(node, name) => {
          setNodes((current) => renameNode(current, node.path, name));
          setRenamePath(null);
          setLastAction(`Renamed ${node.path} to ${name}`);
        }}
        onRenameCancel={() => setRenamePath(null)}
        getContextMenuItems={(node) => [
          {
            id: 'rename',
            label: 'Rename',
            icon: <FilePenIcon size={14} />,
            onSelect: () => setRenamePath(node.path),
          },
          {
            id: 'copy-path',
            label: 'Copy Path',
            icon: <CopyIcon size={14} />,
            onSelect: () => setLastAction(`Copied ${node.path}`),
          },
          {
            id: 'delete',
            label: 'Delete',
            icon: <Trash2Icon size={14} />,
            variant: 'destructive',
            onSelect: () => setLastAction(`Delete ${node.path}`),
          },
        ]}
        dnd={
          enableDnd
            ? {
                canDrop: (sources, targetDir) =>
                  sources.every((source) => canMoveNode(source.path, targetDir?.path ?? '', '')),
                onMove: (sourcePaths, targetDirPath) => {
                  setNodes((current) =>
                    sourcePaths.reduce(
                      (next, sourcePath) => moveNode(next, sourcePath, targetDirPath),
                      current
                    )
                  );
                  setLastAction(
                    `Moved ${sourcePaths.length} item${sourcePaths.length === 1 ? '' : 's'} into ${
                      targetDirPath || 'root'
                    }`
                  );
                },
                onDragStart: (node) => setLastAction(`Dragging ${node.path}`),
                onDragEnd: (node) => setLastAction(`Dropped ${node.path}`),
              }
            : undefined
        }
      />
      <div style={{ fontSize: 12, color: 'var(--em-foreground-muted)' }}>{lastAction}</div>
    </div>
  );
}

function RefDrivenHeaderStory() {
  const treeRef = React.useRef<FileTreeHandle>(null);
  const [nodes, setNodes] = React.useState(() => cloneNodes(baseNodes));
  const { rootNodes, childrenById } = React.useMemo(() => deriveTree(nodes), [nodes]);
  const [expandedPaths, setExpandedPaths] = React.useState<ReadonlySet<string>>(
    () => new Set(['src', 'src/components'])
  );

  return (
    <div
      style={{
        display: 'grid',
        height: '100%',
        minHeight: 0,
        gridTemplateRows: 'auto minmax(0, 1fr)',
      }}
    >
      <div
        style={{ display: 'flex', gap: 6, borderBottom: '1px solid var(--em-border)', padding: 8 }}
      >
        <Button size="xs" variant="secondary" onClick={() => treeRef.current?.startDraft('file')}>
          Add file
        </Button>
        <Button
          size="xs"
          variant="secondary"
          onClick={() => treeRef.current?.startDraft('directory')}
        >
          Add folder
        </Button>
        <Button size="xs" variant="ghost" onClick={() => treeRef.current?.collapseAll()}>
          Collapse all
        </Button>
        <Button size="xs" variant="ghost" onClick={() => treeRef.current?.expandAll()}>
          Expand all
        </Button>
        <Button
          size="xs"
          variant="ghost"
          onClick={() => treeRef.current?.scrollToPath('packages/ui/package.json')}
        >
          Scroll to package.json
        </Button>
      </div>
      <FileTree
        ref={treeRef}
        rootNodes={rootNodes}
        childrenById={childrenById}
        expandedPaths={expandedPaths}
        renderHeader={() => null}
        onToggleExpand={(node, expanded) => {
          setExpandedPaths((current) => togglePath(current, node.path, expanded));
        }}
        onCollapseAll={() => setExpandedPaths(new Set())}
        onExpandAll={(paths) => setExpandedPaths(new Set(paths))}
        onCreateFile={(parentPath, name) => {
          setNodes((current) => addNode(current, parentPath, name, 'file'));
        }}
        onCreateDirectory={(parentPath, name) => {
          setNodes((current) => addNode(current, parentPath, name, 'directory'));
        }}
      />
    </div>
  );
}

interface GitChange {
  path: string;
  status: 'added' | 'modified' | 'deleted' | 'renamed' | 'conflicted';
  additions: number;
  deletions: number;
}

const gitChanges: GitChange[] = [
  {
    path: 'apps/emdash-desktop/src/main/index.ts',
    status: 'modified',
    additions: 24,
    deletions: 8,
  },
  {
    path: 'apps/emdash-desktop/src/renderer/App.tsx',
    status: 'modified',
    additions: 12,
    deletions: 3,
  },
  {
    path: 'packages/ui/src/react/components/file-tree/file-tree.tsx',
    status: 'added',
    additions: 320,
    deletions: 0,
  },
  {
    path: 'packages/ui/src/react/components/file-tree/old-tree.tsx',
    status: 'deleted',
    additions: 0,
    deletions: 87,
  },
  {
    path: 'packages/core/src/runtimes/git/api/status.ts',
    status: 'renamed',
    additions: 6,
    deletions: 2,
  },
  { path: 'pnpm-lock.yaml', status: 'conflicted', additions: 120, deletions: 114 },
];

function MockGitChanges({ mode: initialMode }: { mode: 'tree' | 'flat' }) {
  const [mode, setMode] = React.useState<'tree' | 'flat'>(initialMode);
  const nodes = React.useMemo(() => gitChangesToNodes(gitChanges), []);
  const { rootNodes, childrenById } = React.useMemo(() => deriveTree(nodes), [nodes]);
  const [activePath, setActivePath] = React.useState(gitChanges[0]!.path);
  const [selectedPaths, setSelectedPaths] = React.useState<ReadonlySet<string>>(new Set());
  const changeByPath = React.useMemo(
    () => new Map(gitChanges.map((change) => [change.path, change])),
    []
  );
  const allDirectoryPaths = React.useMemo(
    () => new Set(nodes.filter((node) => node.type === 'directory').map((node) => node.path)),
    [nodes]
  );
  const [expandedPaths, setExpandedPaths] = React.useState<ReadonlySet<string>>(
    () => new Set(allDirectoryPaths)
  );

  return (
    <div
      style={{
        display: 'grid',
        height: '100%',
        minHeight: 0,
        gap: 8,
        gridTemplateRows: 'auto minmax(0, 1fr)',
      }}
    >
      <div style={{ display: 'flex', gap: 6 }}>
        <Button
          size="xs"
          variant={mode === 'tree' ? 'secondary' : 'ghost'}
          onClick={() => setMode('tree')}
        >
          Tree
        </Button>
        <Button
          size="xs"
          variant={mode === 'flat' ? 'secondary' : 'ghost'}
          onClick={() => setMode('flat')}
        >
          List
        </Button>
        <Button
          size="xs"
          variant="ghost"
          disabled={mode === 'flat'}
          onClick={() => setExpandedPaths(new Set(allDirectoryPaths))}
        >
          Expand all
        </Button>
        <Button
          size="xs"
          variant="ghost"
          disabled={mode === 'flat'}
          onClick={() => setExpandedPaths(new Set())}
        >
          Collapse all
        </Button>
      </div>
      <FileTree
        rootNodes={rootNodes}
        childrenById={childrenById}
        expandedPaths={expandedPaths}
        selectedPath={activePath}
        openedPaths={new Set([activePath])}
        mode={mode}
        compactChains
        renderHeader={() => null}
        onToggleExpand={(node, expanded) => {
          setExpandedPaths((current) => togglePath(current, node.path, expanded));
        }}
        onSelect={(node) => {
          if (node && changeByPath.has(node.path)) setActivePath(node.path);
        }}
        onOpenFile={(node) => {
          if (changeByPath.has(node.path)) setActivePath(node.path);
        }}
        onRowHover={(node) => {
          if (changeByPath.has(node.path)) {
            console.info(`Prefetch ${node.path}`);
          }
        }}
        renderDecoration={(node) => {
          const change = changeByPath.get(node.path);
          if (!change) return null;
          return (
            <GitChangeDecoration
              change={change}
              selected={selectedPaths.has(change.path)}
              onToggle={() => {
                setSelectedPaths((current) => {
                  const next = new Set(current);
                  if (next.has(change.path)) next.delete(change.path);
                  else next.add(change.path);
                  return next;
                });
              }}
            />
          );
        }}
        getRowState={(node) => {
          const status = changeByPath.get(node.path)?.status;
          if (!status) return undefined;
          return {
            tone: gitStatusTone(status),
            muted: status === 'deleted',
            strikethrough: status === 'deleted',
          };
        }}
      />
    </div>
  );
}

function gitStatusTone(status: GitChange['status']): FileTreeRowState['tone'] {
  switch (status) {
    case 'added':
      return 'success';
    case 'modified':
      return 'warning';
    case 'deleted':
      return 'error';
    case 'renamed':
      return 'info';
    case 'conflicted':
      return 'error';
  }
}

function GitChangeDecoration({
  change,
  selected,
  onToggle,
}: {
  change: GitChange;
  selected: boolean;
  onToggle(): void;
}) {
  return (
    <span
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        fontSize: 12,
        fontVariantNumeric: 'tabular-nums',
      }}
      aria-label={`${change.additions} lines added, ${change.deletions} lines removed`}
    >
      {change.additions > 0 ? (
        <span style={{ color: 'var(--em-foreground-diff-added)' }}>+{change.additions}</span>
      ) : null}
      {change.deletions > 0 ? (
        <span style={{ color: 'var(--em-foreground-diff-deleted)' }}>-{change.deletions}</span>
      ) : null}
      <button
        type="button"
        aria-label={`Select ${change.path}`}
        onClick={(event) => {
          event.stopPropagation();
          onToggle();
        }}
        style={{
          display: 'inline-flex',
          width: 16,
          height: 16,
          alignItems: 'center',
          justifyContent: 'center',
          border: 0,
          background: 'transparent',
          color: 'inherit',
          padding: 0,
        }}
      >
        {selected ? <CheckSquareIcon size={16} /> : <GitChangeStatusIcon status={change.status} />}
      </button>
    </span>
  );
}

function GitChangeStatusIcon({ status }: { status: GitChange['status'] }) {
  switch (status) {
    case 'added':
      return <SquarePlusIcon size={16} style={{ color: 'var(--em-foreground-diff-added)' }} />;
    case 'modified':
      return <SquareDotIcon size={16} style={{ color: 'var(--em-foreground-diff-modified)' }} />;
    case 'deleted':
      return <SquareMinusIcon size={16} style={{ color: 'var(--em-foreground-diff-deleted)' }} />;
    case 'renamed':
      return <SquareArrowRightIcon size={16} style={{ color: 'var(--em-foreground-muted)' }} />;
    case 'conflicted':
      return <SquareXIcon size={16} style={{ color: 'var(--em-foreground-conflict)' }} />;
  }
}

function StoryFrame({
  height = '28rem',
  note,
  children,
}: {
  height?: string;
  note?: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ display: 'grid', width: '34rem', gap: 8 }}>
      {note ? (
        <p style={{ margin: 0, fontSize: 12, color: 'var(--em-foreground-muted)' }}>{note}</p>
      ) : null}
      <div
        style={{
          height,
          minHeight: 0,
          overflow: 'hidden',
          border: '1px solid var(--em-border)',
          borderRadius: 'var(--em-radius-lg)',
        }}
      >
        {children}
      </div>
    </div>
  );
}

function directory(path: string): FileTreeNode {
  return node(path, 'directory');
}

function file(path: string): FileTreeNode {
  return node(path, 'file');
}

function symlink(
  path: string,
  symlinkTargetKind: NonNullable<FileTreeNode['symlinkTargetKind']>
): FileTreeNode {
  return { ...node(path, 'symlink'), symlink: true, symlinkTargetKind };
}

function node(path: string, type: FileTreeNode['type']): FileTreeNode {
  const normalized = normalizeFileTreePath(path);
  const slash = normalized.lastIndexOf('/');
  const name = slash >= 0 ? normalized.slice(slash + 1) : normalized;
  const parentPath = slash >= 0 ? normalized.slice(0, slash) : '';
  return {
    id: normalized,
    path: normalized,
    name,
    parentId: parentPath || null,
    parentPath,
    depth: parentPath ? parentPath.split('/').length : 0,
    type,
  };
}

function deriveTree(nodes: readonly FileTreeNode[]): {
  rootNodes: FileTreeNode[];
  childrenById: ChildrenById;
} {
  const children = new Map<string | null, FileTreeNode[]>();
  for (const current of nodes) {
    const key = current.parentId || null;
    const entries = children.get(key) ?? [];
    entries.push(current);
    children.set(key, entries);
  }
  return { rootNodes: children.get(null) ?? [], childrenById: children };
}

function addNode(
  nodes: readonly FileTreeNode[],
  parentPath: string,
  name: string,
  type: FileTreeNode['type']
): FileTreeNode[] {
  const path = joinFileTreePath(parentPath, name);
  if (nodes.some((current) => current.path === path)) return [...nodes];
  return [...nodes, node(path, type)];
}

function moveNode(
  nodes: readonly FileTreeNode[],
  sourcePath: string,
  targetDirPath: string
): FileTreeNode[] {
  const source = nodes.find((current) => current.path === sourcePath);
  if (!source) return [...nodes];
  const nextSourcePath = joinFileTreePath(targetDirPath, source.name);
  const sourcePrefix = `${source.path}/`;
  return nodes.map((current) => {
    if (current.path !== source.path && !current.path.startsWith(sourcePrefix)) return current;
    const rest = current.path === source.path ? '' : current.path.slice(source.path.length);
    const nextPath = `${nextSourcePath}${rest}`;
    const next = node(nextPath, current.type);
    return { ...current, ...next };
  });
}

function renameNode(
  nodes: readonly FileTreeNode[],
  sourcePath: string,
  nextName: string
): FileTreeNode[] {
  const source = nodes.find((current) => current.path === sourcePath);
  if (!source) return [...nodes];
  const targetPath = joinFileTreePath(source.parentPath ?? '', nextName);
  const sourcePrefix = `${source.path}/`;
  return nodes.map((current) => {
    if (current.path !== source.path && !current.path.startsWith(sourcePrefix)) return current;
    const rest = current.path === source.path ? '' : current.path.slice(source.path.length);
    const nextPath = `${targetPath}${rest}`;
    const next = node(nextPath, current.type);
    return {
      ...current,
      ...next,
      symlink: current.symlink,
      symlinkTargetKind: current.symlinkTargetKind,
    };
  });
}

function togglePath(
  paths: ReadonlySet<string>,
  path: string,
  expanded: boolean
): ReadonlySet<string> {
  const next = new Set(paths);
  if (expanded) next.add(path);
  else next.delete(path);
  return next;
}

function cloneNodes(nodes: readonly FileTreeNode[]): FileTreeNode[] {
  return nodes.map((current) => ({ ...current }));
}

function gitChangesToNodes(changes: readonly GitChange[]): FileTreeNode[] {
  const dirs = new Set<string>();
  const files = changes.map((change) => {
    const parts = change.path.split('/');
    for (let index = 1; index < parts.length; index += 1) {
      dirs.add(parts.slice(0, index).join('/'));
    }
    return file(change.path);
  });
  return [...[...dirs].map(directory), ...files];
}

function largeTreeNodes(): FileTreeNode[] {
  const nodes: FileTreeNode[] = [];
  for (let area = 0; area < 20; area += 1) {
    const areaPath = `area-${area}`;
    nodes.push(directory(areaPath));
    nodes.push(directory(`${areaPath}/features`));
    for (let fileIndex = 0; fileIndex < 50; fileIndex += 1) {
      nodes.push(file(`${areaPath}/features/component-${fileIndex}.tsx`));
    }
  }
  return nodes;
}
