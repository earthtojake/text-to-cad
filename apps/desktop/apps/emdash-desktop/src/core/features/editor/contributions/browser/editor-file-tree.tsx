import { encodeResourceUri } from '@emdash/core/primitives/path/api';
import { FILE_SEARCH_MAX_QUERY_LENGTH } from '@emdash/core/runtimes/file-search/api';
import { copyNameForConflict, MAX_FILE_UPLOAD_BYTES } from '@emdash/core/runtimes/files/api';
import {
  EmptyState,
  FileTree,
  canMoveNode,
  dedupeDescendantPaths,
  isExpandableFileTreeNode,
  isOpenableFileTreeNode,
  joinFileTreePath,
  normalizeFileTreePath,
  type ChildrenById,
  type FileTreeContextMenuItem,
  type FileTreeHandle,
  type FileTreeHeaderContext,
  type FileTreeNode,
  type FileTreeRootMenuItem,
  type FileTreeRowState,
} from '@emdash/ui/react/components';
import { Button, SearchInput, toast } from '@emdash/ui/react/primitives';
import {
  ClipboardPaste,
  Copy,
  CopyMinus,
  FilePen,
  FilePlus,
  FileText,
  FolderOpen,
  FolderPlus,
  Link2,
  RefreshCw,
  Scissors,
  Trash2,
} from 'lucide-react';
import { observer } from 'mobx-react-lite';
import React, { useCallback, useMemo, useRef, useState } from 'react';
import type { RenderableFileNode } from '@core/features/editor/api/browser/file-tree/tree-utils';
import type { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { FileContentSearchResults } from '@core/features/editor/browser/task-editor/file-content-search';
import type { TreeMutationError } from '@core/features/editor/browser/task-editor/stores/files-store';
import type { FilesStore } from '@core/features/editor/browser/task-editor/stores/files-store';
import { FileIcon } from '@core/features/editor/contributions/browser/file-icon';
import { fileTreeScope } from '@core/features/editor/contributions/scopes';
import { getFilesClient } from '@core/features/files/api/browser/client';
import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import { gitCheckoutStoreToken } from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import { openFile as openWorkbenchFile } from '@core/features/workbench/api/browser/open-file';
import {
  useTaskComposition,
  useWorkspace,
  useWorkspaceId,
} from '@core/features/workbench/api/browser/task-composition-context';
import { useTabLayout } from '@core/features/workbench/api/browser/task-tab-registry';
import { relativeToWorkspace } from '@core/features/workspaces/api/browser/workspace-path';
import { openModal, useOpenModal } from '@core/manifests/browser/modal-api';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import {
  copyTextToClipboard,
  getHostClient,
} from '@core/primitives/desktop-host/browser/host-client';
import {
  hostFileRefFromNativePath,
  nativePathFromHost,
} from '@core/primitives/desktop-runtime/api';
import {
  clearDraggedWorkspaceFile,
  setDraggedWorkspaceFile,
} from '@core/primitives/drag-files/browser/drag-files';
import { detectPlatformContext } from '@core/primitives/keybindings/api';
import { disabled, enabled, hidden, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { useViewScope } from '@core/primitives/view-scopes/react';

const MAX_COPY_FILE_BYTES = 10 * 1024 * 1024;
const PLATFORM = detectPlatformContext().os;
const REVEAL_LABEL =
  PLATFORM === 'mac'
    ? 'Show in Finder'
    : PLATFORM === 'windows'
      ? 'Show in File Explorer'
      : 'Show in File Manager';

type ResultLikeError =
  | TreeMutationError
  | { message?: string; type?: string; paths?: readonly string[] };
type FileTreeClipboard = { mode: 'cut' | 'copy'; paths: string[] };

function resultErrorMessage(error: ResultLikeError | string | undefined): string {
  if (typeof error === 'string') return error;
  if (!error) return 'Unknown error';
  if ('message' in error && error.message) return error.message;
  if ('path' in error && error.path) return `${error.type}: ${error.path}`;
  return error.type ?? 'Unknown error';
}

function conflictPaths(error: ResultLikeError): string[] {
  if (error.type !== 'conflict' || !Array.isArray(error.paths)) return [];
  return [...error.paths];
}

async function importLocalFiles(args: {
  files: FilesStore;
  workspacePath: string;
  sshConnectionId?: string;
  sourceFiles: File[];
  destDirPath: string;
  overwrite?: boolean;
}): Promise<void> {
  const {
    files,
    workspacePath,
    sshConnectionId,
    sourceFiles,
    destDirPath,
    overwrite = false,
  } = args;
  const oversizedFile = sourceFiles.find((file) => file.size > MAX_FILE_UPLOAD_BYTES);
  if (oversizedFile) {
    toast.error('Import failed', {
      description: `${oversizedFile.name} exceeds the 10 MB upload limit.`,
    });
    return;
  }
  const destinations = sourceFiles.map((file) => joinFileTreePath(destDirPath, file.name));
  if (new Set(destinations).size !== destinations.length) {
    toast.error('Import failed', {
      description: 'Multiple dropped files have the same destination name.',
    });
    return;
  }

  const inserted = files.addOptimisticNodes(
    destinations.map((path) => ({
      path,
      type: 'file',
    }))
  );

  const handleFailure = async (error: ResultLikeError) => {
    for (const p of inserted) files.removeNode(p);
    await files.registerDir(destDirPath, true);
    const message = resultErrorMessage(error);
    const existingPaths = conflictPaths(error);
    if (existingPaths.length > 0 && !overwrite) {
      const description =
        existingPaths.length === 1
          ? `${existingPaths[0]} already exists. Replace it with the dropped file?`
          : `${existingPaths.length} files already exist: ${existingPaths.join(', ')}. Replace them with the dropped files?`;
      const outcome = await openModal('confirmActionModal', {
        title: existingPaths.length === 1 ? 'Replace existing file?' : 'Replace existing files?',
        description,
        confirmLabel: 'Replace',
        variant: 'destructive',
      });
      if (outcome.success) {
        void importLocalFiles({
          files,
          workspacePath,
          sshConnectionId,
          sourceFiles,
          destDirPath,
          overwrite: true,
        });
      }
      return;
    }

    toast.error('Import failed', { description: message });
  };

  try {
    const client = await getFilesClient();
    const destinationUri = (destination: string) =>
      encodeResourceUri(hostFileRefFromNativePath(destination, sshConnectionId));
    if (!overwrite) {
      const conflicts: string[] = [];
      for (const destination of destinations) {
        const result = await client.fs.exists({ uri: destinationUri(destination) });
        if (!result.success) {
          await handleFailure(result.error);
          return;
        }
        if (result.data.exists) conflicts.push(relativeToWorkspace(workspacePath, destination));
      }
      if (conflicts.length > 0) {
        await handleFailure({
          type: 'conflict',
          message: 'Files already exist',
          paths: conflicts,
        });
        return;
      }
    }

    for (const [index, sourceFile] of sourceFiles.entries()) {
      const result = await client.fs.upload(
        { uri: destinationUri(destinations[index]), overwrite },
        {
          name: sourceFile.name,
          mimeType: sourceFile.type || 'application/octet-stream',
          size: sourceFile.size,
          lastModified: sourceFile.lastModified,
          source: sourceFile.stream(),
        }
      );
      if (!result.success) {
        await handleFailure(result.error);
        return;
      }
    }
    files.confirmOptimisticNodes(inserted);
  } catch (error) {
    await handleFailure({
      type: 'fs_error',
      message: error instanceof Error ? error.message : 'The file could not be imported.',
    });
  }
}

export const EditorFileTree = observer(function EditorFileTree() {
  const workspace = useWorkspace();
  const workspaceId = useWorkspaceId();
  const taskView = useTaskComposition();
  const tabLayout = useTabLayout();
  const editorView = taskView.editorView;
  const files = editorView.files;
  const liveActionDisabledReason = projectAvailabilityUi.getLiveActionDisabledReason(
    taskView.projectId
  );
  const liveActionsDisabled = Boolean(liveActionDisabledReason);
  const { value: filesSettings } = useAppSettingsKey('files');
  const openConfirmActionModal = useOpenModal('confirmActionModal');
  const [searchQuery, setSearchQuery] = useState('');
  const [renamePath, setRenamePath] = useState<string | null>(null);
  const [selectedPaths, setSelectedPaths] = useState<ReadonlySet<string>>(new Set());
  const [selectionAnchorPath, setSelectionAnchorPath] = useState<string | null>(null);
  const [clipboard, setClipboard] = useState<FileTreeClipboard | null>(null);
  const [pendingDraft, setPendingDraft] = useState<'file' | 'directory' | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const treeRef = useRef<FileTreeHandle>(null);
  const lastSyncedActivePathRef = useRef<string | null>(null);
  const focusRequest = editorView.fileSearchFocusRequest;
  const revealRequest = editorView.revealFileRequest;
  const expandedPaths = editorView.expandedPaths;
  const activeFile = tabLayout.focusedPane.activeResourceOfKind<FileTabResource>('file');
  const openedPaths = useMemo(() => new Set(editorView.openFilePaths), [editorView.openFilePaths]);
  const { rootNodes, childrenById } = useMemo(
    () => mapFileTreeData(files?.rootNodes ?? [], files?.childrenById ?? new Map()),
    [files?.childrenById, files?.rootNodes]
  );
  const nodeByPath = useMemo(
    () => collectFileTreeNodes(rootNodes, childrenById),
    [childrenById, rootNodes]
  );
  const selectedNodes = useMemo(
    () => [...selectedPaths].flatMap((path) => nodeByPath.get(path) ?? []),
    [nodeByPath, selectedPaths]
  );
  const selectionTargetNode = selectionAnchorPath ? nodeByPath.get(selectionAnchorPath) : undefined;
  const creationTargetPath = creationTargetForNode(selectionTargetNode, workspace.path);

  const setSearchInputRef = useCallback(
    (input: HTMLInputElement | null) => {
      searchInputRef.current = input;
      if (!input || focusRequest === 0) return;
      input.focus();
      input.select();
    },
    [focusRequest]
  );

  React.useEffect(() => {
    if (focusRequest === 0) return;
    searchInputRef.current?.focus();
    searchInputRef.current?.select();
  }, [focusRequest]);

  React.useEffect(() => {
    files?.setExclusions(filesSettings?.treeExclude);
  }, [files, filesSettings?.treeExclude]);

  React.useEffect(() => {
    files?.reconcileVisibleScopes(expandedPaths);
  }, [expandedPaths, files]);

  React.useEffect(() => {
    const activePath = activeFile?.path ?? null;
    if (!activePath) {
      lastSyncedActivePathRef.current = null;
      return;
    }
    if (lastSyncedActivePathRef.current === activePath) return;
    // Paths outside the workspace tree simply have no node to select.
    if (!nodeByPath.has(activePath)) return;
    lastSyncedActivePathRef.current = activePath;
    setSelectedPaths(new Set([activePath]));
    setSelectionAnchorPath(activePath);
  }, [activeFile?.path, nodeByPath]);

  React.useEffect(() => {
    setSelectedPaths((current) => prunePathSet(current, nodeByPath));
    setClipboard((current) =>
      current
        ? current.paths.filter((path) => nodeByPath.has(path)).length > 0
          ? { ...current, paths: current.paths.filter((path) => nodeByPath.has(path)) }
          : null
        : null
    );
    setSelectionAnchorPath((current) => (current && nodeByPath.has(current) ? current : null));
  }, [nodeByPath]);

  React.useEffect(() => {
    if (!pendingDraft || searchQuery) return;
    treeRef.current?.startDraft(pendingDraft);
    setPendingDraft(null);
  }, [pendingDraft, searchQuery]);

  React.useEffect(() => {
    if (revealRequest.counter === 0 || !files) return;
    void (async () => {
      const result = await files.revealFile(revealRequest.path);
      if (!result.success) {
        toast.error('Reveal failed', { description: resultErrorMessage(result.error) });
        return;
      }
      editorView.expandPaths(result.data);
      setSelectedPaths(new Set([revealRequest.path]));
      setSelectionAnchorPath(revealRequest.path);
      window.requestAnimationFrame(() => treeRef.current?.scrollToPath(revealRequest.path));
    })();
  }, [editorView, files, revealRequest.counter, revealRequest.path]);

  // Route through the openFile seam (spec §10): sidebar clicks resolve the
  // file's identity here at the edge and never reveal (the tree already shows
  // the file and keeps focus).
  const openFile = (path: string, preview: boolean) => {
    openWorkbenchFile(hostFileRefFromNativePath(path, workspace.sshConnectionId), {
      context: { projectId: taskView.projectId, taskId: taskView.taskId },
      preview,
      target: 'artifact',
    });
  };

  const startDraft = (kind: 'file' | 'directory') => {
    if (searchQuery) {
      setPendingDraft(kind);
      setSearchQuery('');
      return;
    }
    treeRef.current?.startDraft(kind);
  };

  const collapseAll = () => editorView.collapsePaths([...expandedPaths]);
  const expandAll = () => {
    const directoryPaths = [...nodeByPath.values()]
      .filter(isExpandableFileTreeNode)
      .map((node) => node.path);
    editorView.expandPaths(directoryPaths);
  };

  const refresh = async () => {
    if (!files || isRefreshing) return;
    setIsRefreshing(true);
    try {
      const result = await files.refresh();
      if (!result.success) {
        toast.error('Refresh failed', { description: resultErrorMessage(result.error) });
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleCreateFile = async (parentPath: string, name: string) => {
    if (!files) return;
    const path = joinFileTreePath(parentPath, name);
    const result = await files.createFile(path);
    if (!result.success) {
      toast.error('Create failed', { description: resultErrorMessage(result.error) });
      return;
    }
    editorView.expandPath(parentPath);
    openFile(path, false);
    toast('File created');
  };

  const handleCreateDirectory = async (parentPath: string, name: string) => {
    if (!files) return;
    const path = joinFileTreePath(parentPath, name);
    const result = await files.createDirectory(path);
    if (!result.success) {
      toast.error('Create failed', { description: resultErrorMessage(result.error) });
      return;
    }
    editorView.expandPath(parentPath);
    editorView.expandPath(path);
    toast('Folder created');
  };

  const handleRename = async (node: FileTreeNode, name: string) => {
    if (!files) return;
    const targetPath = joinFileTreePath(node.parentPath ?? '', name);
    const result = await files.rename(node.path, name);
    if (!result.success) {
      toast.error('Rename failed', { description: resultErrorMessage(result.error) });
      return;
    }
    await editorView.retargetOpenFiles(node.path, targetPath);
    setRenamePath(null);
    toast(node.type === 'directory' ? 'Folder renamed' : 'File renamed');
  };

  const handleMove = async (sourcePaths: string[], targetDirPath: string) => {
    if (!files) return;
    const deduped = dedupeDescendantPaths(sourcePaths);
    let moved = 0;
    for (const sourcePath of deduped) {
      const targetPath = joinFileTreePath(targetDirPath, basenameFromPath(sourcePath));
      const result = await files.move(sourcePath, targetDirPath);
      if (!result.success) {
        toast.error('Move failed', { description: resultErrorMessage(result.error) });
        return;
      }
      await editorView.retargetOpenFiles(sourcePath, targetPath);
      moved += 1;
    }
    toast(moved === 1 ? 'Item moved' : `${moved} items moved`);
  };

  const closeDeletedFileTabs = (nodes: readonly FileTreeNode[]) => {
    for (const { pane } of taskView.paneLayout.groups) {
      for (const tab of pane.resolvedTabs) {
        if (tab.kind !== 'file') continue;
        const resource = tab.resource as FileTabResource;
        if (
          nodes.some((node) =>
            isPathWithin(
              resource.path,
              node.path,
              node.type === 'directory' || isExpandableFileTreeNode(node)
            )
          )
        ) {
          void pane.closeTab(tab.tabId);
        }
      }
    }
  };

  const confirmDelete = (nodes: readonly FileTreeNode[]) => {
    void (async () => {
      if (!files) return;
      const paths = dedupeDescendantPaths(nodes.map((node) => node.path));
      const targets = paths.flatMap((path) => nodeByPath.get(path) ?? []);
      if (targets.length === 0) return;
      const single = targets.length === 1 ? targets[0] : null;
      const outcome = await openConfirmActionModal({
        title: single
          ? single.type === 'directory'
            ? 'Delete folder?'
            : single.type === 'symlink'
              ? 'Delete link?'
              : 'Delete file?'
          : `Delete ${targets.length} items?`,
        description:
          single?.type === 'directory'
            ? `"${single.path}" and all of its contents will be deleted from the workspace.`
            : single?.type === 'symlink'
              ? `"${single.path}" will be removed from the workspace. Its target will not be deleted.`
              : single
                ? `"${single.path}" will be deleted from the workspace.`
                : `${targets.map((node) => `"${node.path}"`).join(', ')} will be deleted from the workspace.`,
        confirmLabel: 'Delete',
        variant: 'destructive',
      });
      if (!outcome.success) return;
      for (const node of targets) {
        const result = await files.deleteEntry(node.path, node.type === 'directory');
        if (!result.success) {
          await files.registerDir(node.parentPath ?? workspace.path, true);
          toast.error('Delete failed', { description: resultErrorMessage(result.error) });
          return;
        }
      }
      closeDeletedFileTabs(targets);
      setSelectedPaths(new Set());
      setSelectionAnchorPath(null);
      toast(
        single
          ? single.type === 'directory'
            ? 'Folder deleted'
            : single.type === 'symlink'
              ? 'Link deleted'
              : 'File deleted'
          : `${targets.length} items deleted`
      );
    })();
  };

  const copyFile = async (node: FileTreeNode) => {
    if (!isOpenableFileTreeNode(node)) return;
    try {
      const client = await getFilesClient();
      const result = await client.fs.readText({
        uri: encodeResourceUri(hostFileRefFromNativePath(node.path, workspace.sshConnectionId)),
        options: { maxBytes: MAX_COPY_FILE_BYTES },
      });
      if (!result.success) {
        toast.error('Copy failed', { description: resultErrorMessage(result.error) });
        return;
      }
      if (result.data.truncated) {
        toast.error('Copy failed', { description: 'File is too large to copy.' });
        return;
      }
      await copyTextToClipboard(result.data.content);
      toast('File copied');
    } catch (error) {
      toast.error('Copy failed', {
        description: error instanceof Error ? error.message : 'The file could not be copied.',
      });
    }
  };

  const copyPath = async (node: FileTreeNode) => {
    try {
      const client = await getFilesClient();
      const result = await client.fs.realPath({
        uri: encodeResourceUri(hostFileRefFromNativePath(node.path, workspace.sshConnectionId)),
      });
      if (!result.success) {
        toast.error('Copy failed', { description: resultErrorMessage(result.error) });
        return;
      }
      await copyTextToClipboard(nativePathFromHost(result.data.path));
      toast('Path copied');
    } catch (error) {
      toast.error('Copy failed', {
        description: error instanceof Error ? error.message : 'The path could not be copied.',
      });
    }
  };

  const copyRelativePath = async (node: FileTreeNode) => {
    try {
      await copyTextToClipboard(relativeToWorkspace(workspace.path, node.path));
      toast('Relative path copied');
    } catch (error) {
      toast.error('Copy failed', {
        description: error instanceof Error ? error.message : 'The path could not be copied.',
      });
    }
  };

  const revealInFileManager = async (node: FileTreeNode) => {
    try {
      const result = await (
        await getHostClient()
      ).showWorkspaceItemInFolder({
        workspaceId,
        relativePath: relativeToWorkspace(workspace.path, node.path),
      });
      if (!result.success) {
        toast.error('Show failed', { description: resultErrorMessage(result.error) });
      }
    } catch (error) {
      toast.error('Show failed', {
        description: error instanceof Error ? error.message : 'The item could not be shown.',
      });
    }
  };

  const selectionOrNode = (node?: FileTreeNode): FileTreeNode[] => {
    if (node && !selectedPaths.has(node.path)) return [node];
    if (selectedNodes.length > 0) return selectedNodes;
    return node ? [node] : [];
  };

  const cutSelection = (node?: FileTreeNode) => {
    const paths = dedupeDescendantPaths(selectionOrNode(node).map((entry) => entry.path));
    if (paths.length === 0) return;
    setClipboard({ mode: 'cut', paths });
    toast(paths.length === 1 ? 'Item cut' : `${paths.length} items cut`);
  };

  const copySelection = (node?: FileTreeNode) => {
    const paths = dedupeDescendantPaths(selectionOrNode(node).map((entry) => entry.path));
    if (paths.length === 0) return;
    setClipboard({ mode: 'copy', paths });
    toast(paths.length === 1 ? 'Item copied' : `${paths.length} items copied`);
  };

  const pasteClipboard = async (targetDirPath = pasteTargetPath()) => {
    if (!files || !clipboard || clipboard.paths.length === 0) return;
    const existingNames = existingChildNames(
      targetDirPath,
      nodeByPath,
      childrenById,
      workspace.path
    );
    let completed = 0;
    for (const sourcePath of clipboard.paths) {
      const source = nodeByPath.get(sourcePath);
      if (!source) continue;
      const sourceParentPath = source.parentPath ?? workspace.path;
      const sameDirectory =
        normalizeFileTreePath(sourceParentPath) === normalizeFileTreePath(targetDirPath);
      if (clipboard.mode === 'cut' && sameDirectory) continue;
      const hasConflict = nodeByPath.has(
        normalizeFileTreePath(joinFileTreePath(targetDirPath, source.name))
      );
      const nextName =
        clipboard.mode === 'copy' || hasConflict
          ? copyNameForConflict(source.name, existingNames)
          : source.name;
      existingNames.add(nextName);
      const targetPath = joinFileTreePath(targetDirPath, nextName);
      if (clipboard.mode === 'cut' && targetPath === sourcePath) continue;
      const result =
        clipboard.mode === 'cut'
          ? await files.move(sourcePath, targetDirPath, nextName)
          : await files.copy(sourcePath, targetDirPath, nextName);
      if (!result.success) {
        toast.error(clipboard.mode === 'cut' ? 'Move failed' : 'Copy failed', {
          description: resultErrorMessage(result.error),
        });
        return;
      }
      if (clipboard.mode === 'cut') {
        await editorView.retargetOpenFiles(sourcePath, targetPath);
      }
      completed += 1;
    }
    if (clipboard.mode === 'cut') setClipboard(null);
    toast(
      clipboard.mode === 'cut'
        ? completed === 1
          ? 'Item moved'
          : `${completed} items moved`
        : completed === 1
          ? 'Item copied'
          : `${completed} items copied`
    );
  };

  const pasteTargetPath = () => creationTargetPath;

  const renameSelection = () => {
    const target = selectedNodes.length === 1 ? selectedNodes[0] : null;
    if (!target) return;
    setRenamePath(target.path);
  };

  const getContextMenuItems = (
    node: FileTreeNode,
    selection: readonly FileTreeNode[]
  ): FileTreeContextMenuItem[] => {
    const items: FileTreeContextMenuItem[] = [];
    items.push(
      {
        id: 'cut',
        label: 'Cut',
        icon: <Scissors size={14} />,
        onSelect: () => cutSelection(node),
      },
      {
        id: 'copy',
        label: 'Copy',
        icon: <Copy size={14} />,
        onSelect: () => copySelection(node),
      },
      {
        id: 'paste',
        label: 'Paste',
        icon: <ClipboardPaste size={14} />,
        disabled: !clipboard || clipboard.paths.length === 0,
        onSelect: () => void pasteClipboard(creationTargetForNode(node, workspace.path)),
      }
    );
    if (isOpenableFileTreeNode(node)) {
      items.push({
        id: 'copy-file',
        label: 'Copy Contents',
        icon: <FileText size={14} />,
        onSelect: () => void copyFile(node),
      });
    }
    items.push(
      {
        id: 'copy-path',
        label: 'Copy path',
        icon: <Copy size={14} />,
        onSelect: () => void copyPath(node),
      },
      {
        id: 'copy-relative-path',
        label: 'Copy relative path',
        icon: <Copy size={14} />,
        onSelect: () => void copyRelativePath(node),
      }
    );
    if (!workspace.sshConnectionId) {
      items.push({
        id: 'reveal',
        label: REVEAL_LABEL,
        icon: <FolderOpen size={14} />,
        onSelect: () => void revealInFileManager(node),
      });
    }
    items.push(
      {
        id: 'rename',
        label: 'Rename',
        icon: <FilePen size={14} />,
        disabled: liveActionsDisabled || selection.length !== 1,
        onSelect: () => setRenamePath(selection[0]?.path ?? node.path),
      },
      {
        id: 'delete',
        label: 'Delete',
        icon: <Trash2 size={14} />,
        variant: 'destructive',
        disabled: liveActionsDisabled,
        onSelect: () => confirmDelete(selection),
      }
    );
    return items;
  };

  const fileTreeScopeImplementation = {
    'editor.fileTree.rename': () => ({
      availability: () =>
        liveActionDisabledReason
          ? disabled(liveActionDisabledReason)
          : selectedNodes.length === 1
            ? enabled
            : disabled('Select one item'),
      execute: renameSelection,
    }),
    'editor.fileTree.cut': () => ({
      availability: () => (selectedNodes.length > 0 ? enabled : disabled('No selection')),
      execute: () => cutSelection(),
    }),
    'editor.fileTree.copy': () => ({
      availability: () => (selectedNodes.length > 0 ? enabled : disabled('No selection')),
      execute: () => copySelection(),
    }),
    'editor.fileTree.paste': () => ({
      availability: () =>
        liveActionDisabledReason
          ? disabled(liveActionDisabledReason)
          : clipboard
            ? enabled
            : disabled('Nothing to paste'),
      execute: () => void pasteClipboard(),
    }),
    'editor.fileTree.delete': () => ({
      availability: () =>
        liveActionDisabledReason
          ? disabled(liveActionDisabledReason)
          : selectedNodes.length > 0
            ? enabled
            : hidden,
      execute: () => confirmDelete(selectedNodes),
    }),
  } satisfies ViewScopeImpl<typeof fileTreeScope>;
  const { attachRef: attachFileTreeScope } = useViewScope(
    fileTreeScope({ workspaceId }),
    fileTreeScopeImplementation
  );

  const headerContext: FileTreeHeaderContext = {
    targetPath: creationTargetPath,
    startDraft,
    collapseAll,
    expandAll,
  };

  const content =
    files?.observation.kind === 'unavailable' ? (
      <EmptyState
        label="Files unavailable"
        description={liveActionDisabledReason ?? 'The file tree has not been observed yet.'}
      />
    ) : searchQuery && !liveActionsDisabled ? (
      <FileContentSearchResults workspaceId={workspaceId} query={searchQuery} />
    ) : (
      <FileTree
        ref={treeRef}
        rootPath={workspace.path}
        rootNodes={rootNodes}
        childrenById={childrenById}
        expandedPaths={expandedPaths}
        selectedPath={selectionAnchorPath ?? activeFile?.path ?? null}
        selectedPaths={selectedPaths}
        openedPaths={openedPaths}
        isLoading={files?.isLoading ?? true}
        error={files?.error}
        compactChains
        renamePath={renamePath}
        getRootContextMenuItems={() => {
          const items: FileTreeRootMenuItem[] = [
            {
              id: 'new-file',
              label: 'New File',
              icon: <FilePlus size={14} />,
              disabled: liveActionsDisabled,
              onSelect: () =>
                treeRef.current?.startDraft('file', normalizeFileTreePath(workspace.path)),
            },
            {
              id: 'new-folder',
              label: 'New Folder',
              icon: <FolderPlus size={14} />,
              disabled: liveActionsDisabled,
              onSelect: () =>
                treeRef.current?.startDraft('directory', normalizeFileTreePath(workspace.path)),
            },
          ];
          if (clipboard && clipboard.paths.length > 0) {
            items.push({
              id: 'paste',
              label: 'Paste',
              icon: <ClipboardPaste size={14} />,
              disabled: liveActionsDisabled,
              onSelect: () => void pasteClipboard(normalizeFileTreePath(workspace.path)),
            });
          }
          return items;
        }}
        renderHeader={() => null}
        onCollapseAll={collapseAll}
        onExpandAll={(paths) => editorView.expandPaths([...paths])}
        onToggleExpand={(node, expanded) => {
          if (expanded) {
            editorView.expandPath(node.path);
            if (files && isExpandableFileTreeNode(node) && !files.loadedPaths.has(node.path)) {
              void files.registerDir(node.path);
            }
          } else {
            editorView.collapsePath(node.path);
          }
        }}
        onRequestExpand={(path) => {
          editorView.expandPath(path);
          void files?.registerDir(path);
        }}
        onSelectionChange={(paths, anchorPath) => {
          setSelectedPaths(new Set(paths));
          setSelectionAnchorPath(anchorPath);
        }}
        onOpenFile={(node, options) => openFile(node.path, options.preview)}
        onCreateFile={handleCreateFile}
        onCreateDirectory={handleCreateDirectory}
        onRenameSubmit={handleRename}
        onRenameCancel={() => setRenamePath(null)}
        getContextMenuItems={getContextMenuItems}
        renderIcon={(node) => {
          if (node.type === 'file') return <FileIcon filename={node.name} size={12} />;
          if (node.type === 'symlink') return <Link2 size={12} />;
          return null;
        }}
        getRowState={(node) =>
          mergeRowState(
            rowStateForNode(node, workspace.path, workspace),
            clipboard?.mode === 'cut' && clipboard.paths.includes(node.path)
              ? { muted: true }
              : undefined
          )
        }
        dnd={
          files && !liveActionsDisabled
            ? {
                canDrop: (sources, targetDir) =>
                  sources.every((source) =>
                    canMoveNode(source.path, targetDir?.path ?? workspace.path, workspace.path)
                  ),
                onMove: handleMove,
                onDropExternal: (dataTransfer, targetDirPath) => {
                  const sourceFiles = Array.from(dataTransfer.files);
                  if (sourceFiles.length === 0) return;
                  void importLocalFiles({
                    files,
                    workspacePath: workspace.path,
                    sshConnectionId: workspace.sshConnectionId,
                    sourceFiles,
                    destDirPath: targetDirPath,
                  });
                },
                onDragStart: (_node, dataTransfer, selection) => {
                  setDraggedWorkspaceFile(dataTransfer, {
                    workspaceId,
                    targetPaths: selection.map((node) => node.path),
                    targetPlatform: workspace.sshConnectionId ? 'linux' : undefined,
                  });
                },
                onDragEnd: () => clearDraggedWorkspaceFile(),
              }
            : undefined
        }
      />
    );

  return (
    <div ref={attachFileTreeScope} className="flex h-full flex-col overflow-hidden">
      <FileTreeHeaderBar
        context={headerContext}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        setSearchInputRef={setSearchInputRef}
        onRefresh={() => void refresh()}
        isRefreshing={isRefreshing}
        liveActionDisabledReason={liveActionDisabledReason}
      />
      {files?.observation.kind === 'stale' && liveActionDisabledReason && (
        <div
          className="border-b bg-background-secondary px-2 py-1 text-xs text-foreground-muted"
          tabIndex={0}
          role="note"
        >
          {liveActionDisabledReason}
        </div>
      )}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{content}</div>
    </div>
  );
});

export function FileTreeHeaderBar({
  context,
  searchQuery,
  setSearchQuery,
  setSearchInputRef,
  onRefresh,
  isRefreshing,
  liveActionDisabledReason,
}: {
  context: FileTreeHeaderContext;
  searchQuery: string;
  setSearchQuery(value: string): void;
  setSearchInputRef(input: HTMLInputElement | null): void;
  onRefresh(): void;
  isRefreshing: boolean;
  liveActionDisabledReason?: string | null;
}) {
  return (
    <div className="h-[41px] shrink-0 border-b border-border bg-background-secondary px-2">
      <div className="flex h-full items-center gap-1">
        <div className="min-w-0 flex-1">
          <SearchInput
            disabled={Boolean(liveActionDisabledReason)}
            ref={setSearchInputRef}
            size="sm"
            value={searchQuery}
            maxLength={FILE_SEARCH_MAX_QUERY_LENGTH}
            aria-label="Search"
            placeholder="Search"
            className="border-0 bg-transparent shadow-none hover:bg-background-2 focus-visible:bg-transparent focus-visible:ring-1 focus-visible:ring-border-primary"
            onClear={() => setSearchQuery('')}
            onChange={(event) => setSearchQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== 'Escape') return;
              if (searchQuery) setSearchQuery('');
              else event.currentTarget.blur();
            }}
          />
        </div>
        <HeaderAction
          label={liveActionDisabledReason ?? 'New file'}
          disabled={Boolean(liveActionDisabledReason)}
          onClick={() => context.startDraft('file')}
        >
          <FilePlus className="size-3.5" />
        </HeaderAction>
        <HeaderAction
          label={liveActionDisabledReason ?? 'New folder'}
          disabled={Boolean(liveActionDisabledReason)}
          onClick={() => context.startDraft('directory')}
        >
          <FolderPlus className="size-3.5" />
        </HeaderAction>
        <HeaderAction label="Collapse all" onClick={context.collapseAll}>
          <CopyMinus className="size-3.5" />
        </HeaderAction>
        <HeaderAction
          label={liveActionDisabledReason ?? 'Refresh'}
          onClick={onRefresh}
          disabled={isRefreshing || Boolean(liveActionDisabledReason)}
        >
          <RefreshCw className={isRefreshing ? 'size-3.5 animate-spin' : 'size-3.5'} />
        </HeaderAction>
      </div>
    </div>
  );
}

function HeaderAction({
  label,
  onClick,
  disabled = false,
  children,
}: {
  label: string;
  onClick(): void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      icon
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

function mapFileTreeData(
  roots: readonly RenderableFileNode[],
  children: Map<string | null, RenderableFileNode[]>
): { rootNodes: FileTreeNode[]; childrenById: ChildrenById } {
  const mappedChildren = new Map<string | null, FileTreeNode[]>();
  for (const [parentId, entries] of children) {
    mappedChildren.set(parentId, entries.map(toFileTreeNode));
  }
  return {
    rootNodes: roots.map(toFileTreeNode),
    childrenById: mappedChildren,
  };
}

function collectFileTreeNodes(
  roots: readonly FileTreeNode[],
  childrenById: ChildrenById
): Map<string, FileTreeNode> {
  const nodes = new Map<string, FileTreeNode>();
  const visit = (node: FileTreeNode) => {
    nodes.set(normalizeFileTreePath(node.path), node);
    for (const child of childrenById.get(node.id) ?? []) visit(child);
  };
  for (const root of roots) visit(root);
  return nodes;
}

function creationTargetForNode(node: FileTreeNode | undefined, rootPath: string): string {
  if (!node) return normalizeFileTreePath(rootPath);
  if (isExpandableFileTreeNode(node)) return normalizeFileTreePath(node.path);
  return normalizeFileTreePath(node.parentPath ?? rootPath);
}

function prunePathSet(
  paths: ReadonlySet<string>,
  nodeByPath: ReadonlyMap<string, FileTreeNode>
): ReadonlySet<string> {
  const next = new Set([...paths].filter((path) => nodeByPath.has(path)));
  return next.size === paths.size ? paths : next;
}

function mergeRowState(
  base: FileTreeRowState | undefined,
  override: FileTreeRowState | undefined
): FileTreeRowState | undefined {
  if (!base) return override;
  if (!override) return base;
  return { ...base, ...override };
}

function existingChildNames(
  targetDirPath: string,
  nodeByPath: ReadonlyMap<string, FileTreeNode>,
  childrenById: ChildrenById,
  rootPath: string
): Set<string> {
  const normalizedTarget = normalizeFileTreePath(targetDirPath);
  const root = normalizeFileTreePath(rootPath);
  const parentNode = normalizedTarget === root ? null : nodeByPath.get(normalizedTarget);
  if (parentNode === undefined) return new Set();
  const parent = parentNode === null ? null : parentNode.id;
  return new Set((childrenById.get(parent) ?? []).map((node) => node.name));
}

function toFileTreeNode(node: RenderableFileNode): FileTreeNode {
  return {
    id: node.id,
    path: node.path,
    name: node.name,
    parentId: node.parentId,
    parentPath: node.parentPath,
    depth: node.depth,
    type: node.type,
    symlink: Boolean(node.symlink),
    symlinkTargetKind: node.symlink?.targetType,
    childrenLoaded: node.childrenLoaded,
    isHidden: node.isHidden,
    extension: node.extension,
  };
}

function rowStateForNode(
  node: FileTreeNode,
  workspacePath: string,
  workspace: ReturnType<typeof useWorkspace>
): FileTreeRowState | undefined {
  const relNodePath = relativeToWorkspace(workspacePath, node.path);
  const fileStatus = workspace
    .get(gitCheckoutStoreToken)
    .fileChanges?.find((change) => change.path === relNodePath)?.status;
  if (!fileStatus && !node.isHidden) return undefined;
  return {
    muted: node.isHidden || fileStatus === 'deleted',
    strikethrough: fileStatus === 'deleted',
    tone:
      fileStatus === 'added'
        ? 'success'
        : fileStatus === 'modified'
          ? 'warning'
          : fileStatus === 'deleted'
            ? 'error'
            : fileStatus === 'renamed'
              ? 'info'
              : undefined,
  };
}

function isPathWithin(path: string, deletedPath: string, closesDescendants: boolean) {
  return closesDescendants
    ? path === deletedPath || path.startsWith(`${deletedPath}/`)
    : path === deletedPath;
}

function basenameFromPath(path: string): string {
  return normalizeFileTreePath(path).slice(normalizeFileTreePath(path).lastIndexOf('/') + 1);
}
