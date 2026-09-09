import {
  isHeicLikeFile,
  isUnstableDropPath,
} from '@core/features/terminals/api/browser/pty/terminal-image-paths';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { log } from '@core/primitives/logging/browser/logger';

const MAX_DROPPED_BLOB_BYTES = 50 * 1024 * 1024;

export async function resolveDroppedFile(file: File): Promise<string | null> {
  const originalPath = window.electronAPI.getPathForFile(file).trim();
  if (originalPath && !isUnstableDropPath(originalPath) && !isHeicLikeFile(file)) {
    return originalPath;
  }
  if (file.size > MAX_DROPPED_BLOB_BYTES) {
    log.warn('Dropped file is too large to persist', { size: file.size, name: file.name });
    return null;
  }
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const result = await (
      await getHostClient()
    ).persistDroppedBlob({
      bytes,
      name: file.name,
      mimeType: file.type,
    });
    if (result.success) return result.path;
    log.warn('Dropped file persist failed', { error: result.error });
  } catch (error) {
    log.warn('Dropped file arrayBuffer failed', { error });
  }
  return null;
}
