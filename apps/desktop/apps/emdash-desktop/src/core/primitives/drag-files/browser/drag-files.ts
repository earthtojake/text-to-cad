import { NODE_PLATFORMS, type NodePlatform } from '@core/primitives/desktop-host/api/host-contract';

export function hasDraggedFiles(dataTransfer: DataTransfer): boolean {
  return dataTransfer.types.includes('Files');
}

export function getDraggedFilePaths(dataTransfer: DataTransfer): string[] {
  return Array.from(dataTransfer.files)
    .map((file) => window.electronAPI.getPathForFile(file).trim())
    .filter(Boolean);
}

/**
 * In-app drags of workspace files (e.g. from the editor file tree) are tagged
 * with this MIME type. Custom types must be lowercase; browsers lowercase
 * `DataTransfer.types`.
 */
export const WORKSPACE_FILE_DRAG_TYPE = 'application/x-emdash-workspace-file';

export type DraggedWorkspaceFile = {
  workspaceId: string;
  /** Absolute paths in the workspace environment where the target agent runs. */
  targetPaths: string[];
  /** Remote workspaces are Linux targets even when the renderer runs elsewhere. */
  targetPlatform?: NodePlatform;
};

type DraggedWorkspaceFileInput = {
  workspaceId: string;
  /** Absolute paths in the workspace environment where the target agent runs. */
  targetPaths: string[];
  targetPlatform?: NodePlatform;
};

// Electron/Chromium can mangle custom-MIME payloads on drop (getData returns
// whitespace), so the payload also travels through this module-level store —
// drag source and same-window drop targets share the renderer. Consumers still
// require the DataTransfer marker so stale state from a previous drag cannot be
// accepted by an unrelated drop.
let draggedWorkspaceFile: DraggedWorkspaceFile | null = null;

export function setDraggedWorkspaceFile(
  dataTransfer: DataTransfer,
  input: DraggedWorkspaceFileInput
): void {
  const payload: DraggedWorkspaceFile = {
    workspaceId: input.workspaceId,
    targetPaths: input.targetPaths,
    targetPlatform: input.targetPlatform,
  };

  draggedWorkspaceFile = payload;
  dataTransfer.setData(WORKSPACE_FILE_DRAG_TYPE, JSON.stringify(payload));
  dataTransfer.setData('text/plain', payload.targetPaths.join(' '));
  // Prompt drops copy these paths, while the file tree needs the same drag to allow moves.
  dataTransfer.effectAllowed = 'copyMove';
}

/** Call on dragend; drop fires on the target before dragend on the source. */
export function clearDraggedWorkspaceFile(): void {
  draggedWorkspaceFile = null;
}

/** True when this transfer is tagged as an in-app workspace-file drag. */
export function hasDraggedWorkspaceFile(dataTransfer: DataTransfer): boolean {
  return dataTransfer.types.includes(WORKSPACE_FILE_DRAG_TYPE);
}

const nodePlatforms = new Set<NodePlatform>(NODE_PLATFORMS);

function isNodePlatform(value: unknown): value is NodePlatform {
  return typeof value === 'string' && nodePlatforms.has(value as NodePlatform);
}

function isDraggedWorkspaceFile(value: unknown): value is DraggedWorkspaceFile {
  if (!value || typeof value !== 'object') return false;
  const candidate = value as Partial<DraggedWorkspaceFile>;
  return (
    typeof candidate.workspaceId === 'string' &&
    Array.isArray(candidate.targetPaths) &&
    candidate.targetPaths.every((path) => typeof path === 'string') &&
    (candidate.targetPlatform === undefined || isNodePlatform(candidate.targetPlatform))
  );
}

export function getDraggedWorkspaceFile(dataTransfer: DataTransfer): DraggedWorkspaceFile | null {
  if (!hasDraggedWorkspaceFile(dataTransfer)) return null;
  if (draggedWorkspaceFile) return draggedWorkspaceFile;

  try {
    const parsed: unknown = JSON.parse(dataTransfer.getData(WORKSPACE_FILE_DRAG_TYPE));
    return isDraggedWorkspaceFile(parsed) ? parsed : null;
  } catch {
    return null;
  }
}
