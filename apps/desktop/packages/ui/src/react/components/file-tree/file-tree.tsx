import { cx } from '@styles/utilities/cx';
import { ChevronDownIcon, ChevronRightIcon, FileIcon, Link2Icon, Loader2Icon } from 'lucide-react';
import * as React from 'react';
import { resolveFileIconClass } from '../../lib/file-icons';
import {
  buildVisibleTreeRows,
  TreeView,
  type TreeNode,
  type TreeRow,
  type TreeViewHandle,
} from '../../patterns/tree-view';
import { ContextMenu } from '../../primitives/context-menu';
import {
  FileTreeHeader,
  type FileTreeDraftKind,
  type FileTreeHeaderContext,
} from './file-tree-header';
import {
  ancestorPathsFor,
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
  type FileTreeFlatRow,
  type FileTreeNode,
} from './file-tree-utils';
import * as styles from './file-tree.css';

const ROW_HEIGHT = 28;
const ROW_GAP = 2;
const HOVER_EXPAND_MS = 500;
const INTERNAL_DRAG_MIME = 'application/x-emdash-file-tree-path';

export interface FileTreeMenuItemBase {
  id: string;
  label: React.ReactNode;
  icon?: React.ReactNode;
  variant?: 'default' | 'destructive';
  disabled?: boolean;
}

export interface FileTreeContextMenuItem extends FileTreeMenuItemBase {
  onSelect(node: FileTreeNode, selection: readonly FileTreeNode[]): void;
}

export interface FileTreeRootMenuItem extends FileTreeMenuItemBase {
  onSelect(): void;
}

export interface FileTreeDndSpec {
  canDrag?: (node: FileTreeNode) => boolean;
  canDrop?: (sources: readonly FileTreeNode[], targetDir: FileTreeNode | null) => boolean;
  onDragStart?: (
    node: FileTreeNode,
    dataTransfer: DataTransfer,
    selection: readonly FileTreeNode[]
  ) => void;
  onDragEnd?: (
    node: FileTreeNode,
    dataTransfer: DataTransfer,
    selection: readonly FileTreeNode[]
  ) => void;
  onMove(sourcePaths: string[], targetDirPath: string): void | Promise<void>;
  onDropExternal?: (dataTransfer: DataTransfer, targetDirPath: string) => void;
}

export interface FileTreeRowState {
  muted?: boolean;
  strikethrough?: boolean;
  tone?: 'success' | 'warning' | 'error' | 'info';
}

export interface FileTreeIconState {
  expanded: boolean;
}

export interface FileTreeOpenOptions {
  preview: boolean;
}

export interface FileTreeProps {
  rootPath?: string;
  rootNodes: readonly FileTreeNode[];
  childrenById: ChildrenById;
  expandedPaths?: ReadonlySet<string>;
  selectedPath?: string | null;
  selectedPaths?: ReadonlySet<string>;
  openedPaths?: ReadonlySet<string>;
  isLoading?: boolean;
  error?: React.ReactNode;
  mode?: 'tree' | 'flat';
  compactChains?: boolean;
  defaultExpanded?: 'all' | 'none';
  dnd?: FileTreeDndSpec;
  className?: string;
  renamePath?: string | null;
  onCollapseAll?: () => void;
  onExpandAll?: (directoryPaths: ReadonlySet<string>) => void;
  onToggleExpand?: (node: FileTreeNode, expanded: boolean) => void;
  onSelect?: (node: FileTreeNode | null) => void;
  onSelectionChange?: (paths: ReadonlySet<string>, anchorPath: string | null) => void;
  onOpenFile?: (node: FileTreeNode, options: FileTreeOpenOptions) => void;
  onCreateFile?: (parentPath: string, name: string) => void | Promise<void>;
  onCreateDirectory?: (parentPath: string, name: string) => void | Promise<void>;
  onRenameSubmit?: (node: FileTreeNode, name: string) => void | Promise<void>;
  onRenameCancel?: () => void;
  onRequestExpand?: (path: string) => void;
  onRowHover?: (node: FileTreeNode) => void;
  getContextMenuItems?: (
    node: FileTreeNode,
    selection: readonly FileTreeNode[]
  ) => readonly FileTreeContextMenuItem[] | null;
  getRootContextMenuItems?: () => readonly FileTreeRootMenuItem[] | null;
  renderIcon?: (node: FileTreeNode, state: FileTreeIconState) => React.ReactNode;
  renderHeader?: (context: FileTreeHeaderContext) => React.ReactNode;
  renderDecoration?: (node: FileTreeNode) => React.ReactNode;
  getRowState?: (node: FileTreeNode) => FileTreeRowState | undefined;
}

export interface FileTreeHandle {
  startDraft(kind: FileTreeDraftKind, overridePath?: string): void;
  collapseAll(): void;
  expandAll(): void;
  scrollToPath(path: string): void;
}

interface DraftState {
  kind: FileTreeDraftKind;
  parentPath: string;
}

type RenderableData =
  | { kind: 'node'; node: FileTreeNode; flatDirectory?: string }
  | { kind: 'draft'; draft: DraftState };

function FileTreeInner(
  {
    rootPath = '',
    rootNodes,
    childrenById,
    expandedPaths,
    selectedPath,
    selectedPaths,
    openedPaths,
    isLoading = false,
    error,
    mode = 'tree',
    compactChains = false,
    defaultExpanded = 'none',
    dnd,
    className,
    renamePath,
    onCollapseAll,
    onExpandAll,
    onToggleExpand,
    onSelect,
    onSelectionChange,
    onOpenFile,
    onCreateFile,
    onCreateDirectory,
    onRenameSubmit,
    onRenameCancel,
    onRequestExpand,
    onRowHover,
    getContextMenuItems,
    getRootContextMenuItems,
    renderIcon,
    renderHeader,
    renderDecoration,
    getRowState,
  }: FileTreeProps,
  ref: React.ForwardedRef<FileTreeHandle>
) {
  const normalizedRootPath = normalizeFileTreePath(rootPath);
  const allNodes = React.useMemo(
    () => collectNodes(rootNodes, childrenById),
    [childrenById, rootNodes]
  );
  const nodesByPath = React.useMemo(
    () => new Map(allNodes.map((node) => [normalizeFileTreePath(node.path), node])),
    [allNodes]
  );
  const directoryPaths = React.useMemo(
    () =>
      new Set(
        allNodes.filter(isExpandableFileTreeNode).map((node) => normalizeFileTreePath(node.path))
      ),
    [allNodes]
  );
  const [internalExpandedPaths, setInternalExpandedPaths] = React.useState<ReadonlySet<string>>(
    () => (defaultExpanded === 'all' ? directoryPaths : new Set())
  );
  const [draft, setDraft] = React.useState<DraftState | null>(null);
  const [dragSourcePaths, setDragSourcePaths] = React.useState<readonly string[]>([]);
  const [dropTargetPath, setDropTargetPath] = React.useState<string | null>(null);
  const [pendingMovePaths, setPendingMovePaths] = React.useState<ReadonlySet<string>>(new Set());
  const hoverExpandTimerRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  const treeViewRef = React.useRef<TreeViewHandle>(null);

  React.useEffect(() => {
    if (expandedPaths) return;
    setInternalExpandedPaths(defaultExpanded === 'all' ? directoryPaths : new Set());
  }, [defaultExpanded, directoryPaths, expandedPaths]);

  React.useEffect(() => () => clearHoverExpandTimer(hoverExpandTimerRef), []);

  const effectiveExpandedPaths = React.useMemo(
    () => normalizePathSet(expandedPaths ?? internalExpandedPaths),
    [expandedPaths, internalExpandedPaths]
  );
  const normalizedOpenedPaths = React.useMemo(
    () => normalizePathSet(openedPaths ?? new Set()),
    [openedPaths]
  );
  const normalizedSelectedPath = selectedPath ? normalizeFileTreePath(selectedPath) : null;
  const normalizedSelectedPaths = React.useMemo(() => {
    if (selectedPaths) return normalizePathSet(selectedPaths);
    return normalizedSelectedPath ? new Set([normalizedSelectedPath]) : new Set<string>();
  }, [normalizedSelectedPath, selectedPaths]);
  const normalizedRenamePath = renamePath ? normalizeFileTreePath(renamePath) : null;
  const selectedNode = normalizedSelectedPath ? nodesByPath.get(normalizedSelectedPath) : undefined;
  const targetPath = creationTargetPath(selectedNode, normalizedRootPath);

  const treeNodes = React.useMemo(
    () =>
      mode === 'flat'
        ? buildFlatRenderableNodes(rootNodes, childrenById, draft)
        : buildRenderableTreeNodes(rootNodes, childrenById, draft, targetPath, normalizedRootPath),
    [childrenById, draft, mode, normalizedRootPath, rootNodes, targetPath]
  );
  const visibleRows = React.useMemo(
    () => buildVisibleTreeRows(treeNodes, effectiveExpandedPaths, { compactChains }),
    [compactChains, effectiveExpandedPaths, treeNodes]
  );
  const visibleNodePaths = React.useMemo(
    () =>
      visibleRows.flatMap((row) =>
        row.node.data.kind === 'node' ? [normalizeFileTreePath(row.node.data.node.path)] : []
      ),
    [visibleRows]
  );
  const selectedNodes = React.useMemo(
    () => [...normalizedSelectedPaths].flatMap((path) => nodesByPath.get(path) ?? []),
    [nodesByPath, normalizedSelectedPaths]
  );

  React.useImperativeHandle(
    ref,
    () => ({
      startDraft,
      collapseAll,
      expandAll,
      scrollToPath(path) {
        treeViewRef.current?.scrollToId(normalizeFileTreePath(path), { align: 'center' });
      },
    }),
    [startDraft, collapseAll, expandAll]
  );

  const header =
    renderHeader === undefined ? (
      <FileTreeHeader
        targetPath={targetPath}
        startDraft={startDraft}
        collapseAll={collapseAll}
        expandAll={expandAll}
      />
    ) : (
      renderHeader({ targetPath, startDraft, collapseAll, expandAll })
    );

  if (isLoading) {
    return (
      <section className={cx(styles.root, className)} aria-label="File tree">
        {header}
        <FileTreeState>
          <Loader2Icon aria-hidden className={styles.spinner} />
          Loading files
        </FileTreeState>
      </section>
    );
  }

  if (error) {
    return (
      <section className={cx(styles.root, className)} aria-label="File tree">
        {header}
        <FileTreeState error>{error}</FileTreeState>
      </section>
    );
  }

  const empty = rootNodes.length === 0 && !draft;

  const bodyInnerContent = (
    <>
      {empty ? (
        <FileTreeState>Empty folder</FileTreeState>
      ) : (
        <TreeView
          ref={treeViewRef}
          nodes={treeNodes}
          expandedIds={effectiveExpandedPaths}
          compactChains={compactChains}
          estimateSize={ROW_HEIGHT}
          gap={ROW_GAP}
          overscan={8}
          className={styles.treeViewport}
          renderRow={(row) => renderTreeRow(row)}
        />
      )}
      {dropTargetPath === normalizedRootPath ? <div className={styles.rootDropTarget} /> : null}
    </>
  );

  const rootMenuItems = getRootContextMenuItems?.() ?? null;
  const bodyProps: React.HTMLAttributes<HTMLDivElement> = {
    className: styles.body,
    onDragOver: (event) => handleDragOver(null, event),
    onDragLeave: (event) => {
      if (event.currentTarget === event.target) setDropTargetPath(null);
    },
    onDrop: (event) => handleDrop(null, event),
  };

  return (
    <section className={cx(styles.root, className)} aria-label="File tree">
      {header}
      {rootMenuItems?.length ? (
        <ContextMenu.Root>
          <ContextMenu.Trigger {...bodyProps}>{bodyInnerContent}</ContextMenu.Trigger>
          <ContextMenu.Content>
            {rootMenuItems.map((item) => (
              <ContextMenu.Item
                key={item.id}
                disabled={item.disabled}
                variant={item.variant}
                onClick={item.onSelect}
              >
                {item.icon}
                {item.label}
              </ContextMenu.Item>
            ))}
          </ContextMenu.Content>
        </ContextMenu.Root>
      ) : (
        <div {...bodyProps}>{bodyInnerContent}</div>
      )}
    </section>
  );

  function renderTreeRow(row: TreeRow<RenderableData>) {
    if (row.node.data.kind === 'draft') {
      return (
        <DraftRow
          kind={row.node.data.draft.kind}
          depth={row.depth}
          onCommit={commitDraft}
          onCancel={() => setDraft(null)}
        />
      );
    }

    const node = row.node.data.node;
    if (onRenameSubmit && normalizeFileTreePath(node.path) === normalizedRenamePath) {
      return (
        <DraftRow
          kind={node.type === 'directory' ? 'directory' : 'file'}
          depth={row.depth}
          initialValue={node.name}
          placeholder="New name"
          onCommit={(name) => commitRename(node, name)}
          onCancel={() => onRenameCancel?.()}
        />
      );
    }

    const isExpanded = row.isExpanded;
    const normalizedPath = normalizeFileTreePath(node.path);
    const isSelected = normalizedSelectedPaths.has(normalizedPath);
    const isOpened = normalizedOpenedPaths.has(normalizeFileTreePath(node.path));
    const state = getRowState?.(node);
    const contextSelection = isSelected ? selectedNodes : [node];
    const menuItems = getContextMenuItems?.(node, contextSelection) ?? null;
    const icon = renderIcon ? renderIcon(node, { expanded: isExpanded }) : defaultIcon(node);
    const content = (
      <button
        type="button"
        className={styles.row}
        style={rowIndentStyle(row.depth)}
        draggable={dnd ? (dnd.canDrag?.(node) ?? true) : undefined}
        data-selected={isSelected || undefined}
        data-opened={!isSelected && isOpened ? true : undefined}
        data-drop-target={dropTargetPath === normalizeFileTreePath(node.path) || undefined}
        data-pending={pendingMovePaths.has(normalizedPath) || undefined}
        onClick={(event) => handleNodeClick(node, isExpanded, event)}
        onContextMenu={() => handleNodeContextMenu(node, isSelected)}
        onDoubleClick={() => handleNodeDoubleClick(node)}
        onMouseEnter={() => onRowHover?.(node)}
        onDragStart={(event) => handleDragStart(node, event)}
        onDragOver={(event) => handleDragOver(node, event)}
        onDragLeave={() => setDropTargetPath(null)}
        onDrop={(event) => handleDrop(node, event)}
        onDragEnd={(event) => {
          dnd?.onDragEnd?.(node, event.dataTransfer, contextSelection);
          clearHoverExpandTimer(hoverExpandTimerRef);
          setDragSourcePaths([]);
          setDropTargetPath(null);
        }}
      >
        {Array.from({ length: row.depth }, (_, level) => (
          <span
            key={level}
            className={styles.indentGuide}
            style={indentGuideStyle(level)}
            aria-hidden
          />
        ))}
        {isExpandableFileTreeNode(node) ? (
          <span className={styles.chevron} aria-hidden>
            {isExpanded ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
          </span>
        ) : (
          <span className={styles.chevron} aria-hidden>
            {icon}
          </span>
        )}
        <span className={styles.label}>
          <span
            className={cx(
              styles.name,
              state?.muted && styles.muted,
              state?.strikethrough && styles.strikethrough
            )}
            data-tone={state?.tone}
          >
            {displayName(row)}
          </span>
          {row.node.data.flatDirectory ? (
            <span className={styles.secondary}>{row.node.data.flatDirectory}</span>
          ) : null}
        </span>
        {renderDecoration ? (
          <span className={styles.decoration}>{renderDecoration(node)}</span>
        ) : null}
      </button>
    );

    if (!menuItems?.length) return content;
    return (
      <ContextMenu.Root>
        <ContextMenu.Trigger className={styles.rowWrapper}>{content}</ContextMenu.Trigger>
        <ContextMenu.Content>
          {menuItems.map((item) => (
            <ContextMenu.Item
              key={item.id}
              disabled={item.disabled}
              variant={item.variant}
              onClick={() => item.onSelect(node, contextSelection)}
            >
              {item.icon}
              {item.label}
            </ContextMenu.Item>
          ))}
        </ContextMenu.Content>
      </ContextMenu.Root>
    );
  }

  function startDraft(kind: FileTreeDraftKind, overridePath?: string) {
    const resolvedPath =
      overridePath !== undefined ? normalizeFileTreePath(overridePath) : targetPath;
    setDraft({ kind, parentPath: resolvedPath });
    if (resolvedPath) requestExpandPath(resolvedPath);
  }

  function collapseAll() {
    if (!expandedPaths) setInternalExpandedPaths(new Set());
    onCollapseAll?.();
  }

  function expandAll() {
    if (!expandedPaths) setInternalExpandedPaths(new Set(directoryPaths));
    onExpandAll?.(directoryPaths);
  }

  function handleNodeClick(
    node: FileTreeNode,
    isExpanded: boolean,
    event: React.MouseEvent<HTMLButtonElement>
  ) {
    updateSelection(node, event);
    if (event.metaKey || event.ctrlKey || event.shiftKey) return;
    if (isExpandableFileTreeNode(node)) {
      setExpanded(node, !isExpanded);
      return;
    }
    if (isOpenableFileTreeNode(node)) onOpenFile?.(node, { preview: true });
  }

  function handleNodeContextMenu(node: FileTreeNode, isSelected: boolean) {
    if (isSelected) return;
    const path = normalizeFileTreePath(node.path);
    onSelectionChange?.(new Set([path]), path);
    onSelect?.(node);
  }

  function updateSelection(node: FileTreeNode, event: React.MouseEvent<HTMLButtonElement>) {
    const path = normalizeFileTreePath(node.path);
    let next: ReadonlySet<string>;
    if (event.shiftKey) {
      next = new Set(selectionRange(visibleNodePaths, normalizedSelectedPath, path));
    } else if (event.metaKey || event.ctrlKey) {
      const toggled = new Set(normalizedSelectedPaths);
      if (toggled.has(path)) toggled.delete(path);
      else toggled.add(path);
      next = toggled;
    } else {
      next = new Set([path]);
    }
    onSelectionChange?.(next, path);
    onSelect?.(node);
  }

  function handleNodeDoubleClick(node: FileTreeNode) {
    if (isOpenableFileTreeNode(node)) onOpenFile?.(node, { preview: false });
  }

  function setExpanded(node: FileTreeNode, expanded: boolean) {
    const path = normalizeFileTreePath(node.path);
    // A compacted row stands for a chain of single-child directories, and it only
    // renders as expanded once every segment is expanded. Collapsing the deepest
    // segment is enough to close the row again.
    const paths = expanded ? [...ancestorPathsFor(path, normalizedRootPath), path] : [path];

    if (!expandedPaths) {
      setInternalExpandedPaths((current) => {
        const next = new Set(current);
        for (const target of paths) {
          if (expanded) next.add(target);
          else next.delete(target);
        }
        return next;
      });
    }

    if (!onToggleExpand) return;
    for (const target of paths) {
      const targetNode = target === path ? node : nodesByPath.get(target);
      if (targetNode) onToggleExpand(targetNode, expanded);
    }
  }

  function requestExpandPath(path: string) {
    const node = nodesByPath.get(normalizeFileTreePath(path));
    if (!node || !isExpandableFileTreeNode(node)) return;
    if (effectiveExpandedPaths.has(normalizeFileTreePath(node.path))) return;
    onRequestExpand?.(normalizeFileTreePath(path));
    setExpanded(node, true);
  }

  async function commitDraft(name: string) {
    if (!draft) return;
    const trimmed = name.trim();
    if (!trimmed) {
      setDraft(null);
      return;
    }
    if (draft.kind === 'file') await onCreateFile?.(draft.parentPath, trimmed);
    else await onCreateDirectory?.(draft.parentPath, trimmed);
    setDraft(null);
  }

  async function commitRename(node: FileTreeNode, name: string) {
    const trimmed = name.trim();
    if (!trimmed || trimmed === node.name) {
      onRenameCancel?.();
      return;
    }
    await onRenameSubmit?.(node, trimmed);
    onRenameCancel?.();
  }

  function handleDragStart(node: FileTreeNode, event: React.DragEvent<HTMLButtonElement>) {
    if (!dnd || !(dnd.canDrag?.(node) ?? true)) {
      event.preventDefault();
      return;
    }
    const path = normalizeFileTreePath(node.path);
    const selectedSourcePaths = normalizedSelectedPaths.has(path)
      ? [...normalizedSelectedPaths]
      : [path];
    const sources = selectedSourcePaths
      .flatMap((sourcePath) => nodesByPath.get(sourcePath) ?? [])
      .filter((source) => dnd.canDrag?.(source) ?? true);
    if (sources.length === 0) {
      event.preventDefault();
      return;
    }
    const sourcePaths = sources.map((source) => normalizeFileTreePath(source.path));
    setDragSourcePaths(sourcePaths);
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData(INTERNAL_DRAG_MIME, JSON.stringify(sourcePaths));
    event.dataTransfer.setData('text/plain', sourcePaths.join('\n'));
    dnd.onDragStart?.(node, event.dataTransfer, sources);
  }

  function handleDragOver(targetNode: FileTreeNode | null, event: React.DragEvent<HTMLElement>) {
    if (!dnd) return;
    const target = resolveDropTargetDir(targetNode, nodesByPath, normalizedRootPath);
    const sourcePaths = dragSourcePaths.length
      ? dragSourcePaths
      : parseDragSourcePaths(event.dataTransfer);
    const canDrop = sourcePaths.length
      ? canDropInternal(sourcePaths, target)
      : Boolean(dnd.onDropExternal);
    if (!canDrop) return;

    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = sourcePaths.length ? 'move' : 'copy';
    setDropTargetPath(target.targetDirPath);
    scheduleHoverExpand(target.targetDir);
  }

  function handleDrop(targetNode: FileTreeNode | null, event: React.DragEvent<HTMLElement>) {
    if (!dnd) return;
    const target = resolveDropTargetDir(targetNode, nodesByPath, normalizedRootPath);
    const sourcePaths = dragSourcePaths.length
      ? dragSourcePaths
      : parseDragSourcePaths(event.dataTransfer);

    event.preventDefault();
    event.stopPropagation();
    clearHoverExpandTimer(hoverExpandTimerRef);
    setDropTargetPath(null);
    setDragSourcePaths([]);

    if (sourcePaths.length && canDropInternal(sourcePaths, target)) {
      void moveInternal(sourcePaths, target.targetDirPath);
      return;
    }

    if (!sourcePaths.length && dnd.onDropExternal) {
      dnd.onDropExternal(event.dataTransfer, target.targetDirPath);
    }
  }

  function canDropInternal(
    sourcePaths: readonly string[],
    target: { targetDir: FileTreeNode | null; targetDirPath: string }
  ) {
    const sources = dedupeDescendantPaths(sourcePaths).flatMap(
      (sourcePath) => nodesByPath.get(sourcePath) ?? []
    );
    if (sources.length === 0) return false;
    for (const source of sources) {
      if (!canMoveNode(source.path, target.targetDirPath, normalizedRootPath)) return false;
    }
    return dnd?.canDrop?.(sources, target.targetDir) ?? true;
  }

  async function moveInternal(sourcePaths: readonly string[], targetDirPath: string) {
    const normalizedSources = dedupeDescendantPaths(sourcePaths);
    setPendingMovePaths(new Set(normalizedSources));
    try {
      await dnd?.onMove(normalizedSources, targetDirPath);
    } finally {
      setPendingMovePaths(new Set());
    }
  }

  function scheduleHoverExpand(targetDir: FileTreeNode | null) {
    clearHoverExpandTimer(hoverExpandTimerRef);
    if (!targetDir || effectiveExpandedPaths.has(normalizeFileTreePath(targetDir.path))) return;
    hoverExpandTimerRef.current = setTimeout(() => {
      setExpanded(targetDir, true);
    }, HOVER_EXPAND_MS);
  }
}

export const FileTree = React.forwardRef(FileTreeInner);

function DraftRow({
  kind,
  depth,
  initialValue = '',
  placeholder,
  onCommit,
  onCancel,
}: {
  kind: FileTreeDraftKind;
  depth: number;
  initialValue?: string;
  placeholder?: string;
  onCommit(name: string): void | Promise<void>;
  onCancel(): void;
}) {
  const [value, setValue] = React.useState(initialValue);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const settledRef = React.useRef(false);

  React.useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  const commit = React.useCallback(() => {
    if (settledRef.current) return;
    settledRef.current = true;
    void onCommit(value);
  }, [onCommit, value]);

  const cancel = React.useCallback(() => {
    if (settledRef.current) return;
    settledRef.current = true;
    onCancel();
  }, [onCancel]);

  return (
    <div className={cx(styles.row, styles.draftRow)} style={rowIndentStyle(depth)}>
      {Array.from({ length: depth }, (_, level) => (
        <span
          key={level}
          className={styles.indentGuide}
          style={indentGuideStyle(level)}
          aria-hidden
        />
      ))}
      <span className={styles.chevron} aria-hidden>
        {kind === 'directory' ? <ChevronRightIcon size={14} /> : <FileIcon size={12} />}
      </span>
      <input
        ref={inputRef}
        className={styles.draftInput}
        value={value}
        placeholder={placeholder ?? (kind === 'directory' ? 'Folder name' : 'File name')}
        onChange={(event) => setValue(event.currentTarget.value)}
        onBlur={() => {
          if (value.trim()) commit();
          else cancel();
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            cancel();
          } else if (event.key === 'Enter') {
            event.preventDefault();
            commit();
          }
        }}
      />
    </div>
  );
}

function FileTreeState({
  error = false,
  children,
}: {
  error?: boolean;
  children: React.ReactNode;
}) {
  return <div className={cx(styles.state, error && styles.stateError)}>{children}</div>;
}

function defaultIcon(node: FileTreeNode) {
  if (node.type === 'directory') return null;
  if (node.type === 'symlink') return <Link2Icon size={12} />;
  const iconClass = resolveFileIconClass(node.name);
  if (iconClass) return <i className={cx(styles.devicon, iconClass)} />;
  return <FileIcon className={styles.fileIcon} size={12} />;
}

function displayName(row: TreeRow<RenderableData>): string {
  if (row.node.data.kind !== 'node') return '';
  if (row.chain.length <= 1) return row.node.data.node.name;
  return row.chain
    .map((segment) => (segment.data.kind === 'node' ? segment.data.node.name : ''))
    .filter(Boolean)
    .join('/');
}

function buildRenderableTreeNodes(
  rootNodes: readonly FileTreeNode[],
  childrenById: ChildrenById,
  draft: DraftState | null,
  targetPath: string,
  rootPath: string
): TreeNode<RenderableData>[] {
  const sortedRoots = sortFileNodes(rootNodes);
  const roots =
    draft && targetPath === rootPath
      ? [
          draftTreeNode(draft),
          ...sortedRoots.map((node) => toRenderableTreeNode(node, childrenById, draft)),
        ]
      : sortedRoots.map((node) => toRenderableTreeNode(node, childrenById, draft));
  return roots;
}

function toRenderableTreeNode(
  node: FileTreeNode,
  childrenById: ChildrenById,
  draft: DraftState | null
): TreeNode<RenderableData> {
  if (!isExpandableFileTreeNode(node)) {
    return { id: normalizeFileTreePath(node.path), data: { kind: 'node', node } };
  }

  const children = sortFileNodes(childrenById.get(node.id) ?? []).map((child) =>
    toRenderableTreeNode(child, childrenById, draft)
  );
  const normalizedPath = normalizeFileTreePath(node.path);
  const nextChildren =
    draft && draft.parentPath === normalizedPath ? [draftTreeNode(draft), ...children] : children;

  return {
    id: normalizedPath,
    data: { kind: 'node', node },
    children: nextChildren,
  };
}

function buildFlatRenderableNodes(
  rootNodes: readonly FileTreeNode[],
  childrenById: ChildrenById,
  draft: DraftState | null
): TreeNode<RenderableData>[] {
  const rows = buildFlatFileRows(rootNodes, childrenById);
  const nodes = rows.map((row) => flatTreeNode(row));
  return draft ? [draftTreeNode(draft), ...nodes] : nodes;
}

function flatTreeNode(row: FileTreeFlatRow): TreeNode<RenderableData> {
  return {
    id: normalizeFileTreePath(row.node.path),
    data: { kind: 'node', node: row.node, flatDirectory: row.directory },
  };
}

function draftTreeNode(draft: DraftState): TreeNode<RenderableData> {
  return {
    id: `__draft__:${draft.kind}:${draft.parentPath}`,
    data: { kind: 'draft', draft },
  };
}

function collectNodes(
  rootNodes: readonly FileTreeNode[],
  childrenById: ChildrenById
): FileTreeNode[] {
  const nodes: FileTreeNode[] = [];
  const visit = (node: FileTreeNode) => {
    nodes.push(node);
    for (const child of childrenById.get(node.id) ?? []) visit(child);
  };
  for (const node of rootNodes) visit(node);
  return nodes;
}

function normalizePathSet(paths: ReadonlySet<string>): ReadonlySet<string> {
  return new Set([...paths].map(normalizeFileTreePath));
}

function rowIndentStyle(depth: number): React.CSSProperties {
  return {
    '--file-tree-row-indent': `${depth * 12 + 4}px`,
  } as React.CSSProperties;
}

function indentGuideStyle(level: number): React.CSSProperties {
  return {
    left: `${level * 12 + 11}px`,
  };
}

function parseDragSourcePaths(dataTransfer: DataTransfer): string[] {
  const value = dataTransfer.getData(INTERNAL_DRAG_MIME);
  if (!value) return [];
  try {
    const parsed: unknown = JSON.parse(value);
    if (Array.isArray(parsed)) {
      return parsed.filter((path): path is string => typeof path === 'string');
    }
  } catch {
    return [value];
  }
  return [];
}

function clearHoverExpandTimer(ref: React.MutableRefObject<ReturnType<typeof setTimeout> | null>) {
  if (!ref.current) return;
  clearTimeout(ref.current);
  ref.current = null;
}
