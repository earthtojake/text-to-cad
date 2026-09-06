import { describe, expect, it } from 'vitest';
import {
  clearDraggedWorkspaceFile,
  getDraggedWorkspaceFile,
  hasDraggedWorkspaceFile,
  setDraggedWorkspaceFile,
} from '@core/primitives/drag-files/browser/drag-files';

function makeDataTransfer(): DataTransfer {
  const values = new Map<string, string>();
  const transfer = {
    types: [] as string[],
    files: [] as unknown as FileList,
    effectAllowed: 'all',
    setData(type: string, value: string) {
      if (!values.has(type)) this.types.push(type);
      values.set(type, value);
    },
    getData(type: string) {
      return values.get(type) ?? '';
    },
  };
  return transfer as unknown as DataTransfer;
}

describe('drag-files', () => {
  it('carries workspace file payloads for same-window drops', () => {
    const dataTransfer = makeDataTransfer();

    setDraggedWorkspaceFile(dataTransfer, {
      workspaceId: 'workspace-1',
      targetPaths: ['/remote/repo/src/index.ts', '/remote/repo/src/app.ts'],
      targetPlatform: 'linux',
    });

    expect(hasDraggedWorkspaceFile(dataTransfer)).toBe(true);
    expect(getDraggedWorkspaceFile(dataTransfer)).toEqual({
      workspaceId: 'workspace-1',
      targetPaths: ['/remote/repo/src/index.ts', '/remote/repo/src/app.ts'],
      targetPlatform: 'linux',
    });
    expect(dataTransfer.getData('text/plain')).toBe(
      '/remote/repo/src/index.ts /remote/repo/src/app.ts'
    );
    expect(dataTransfer.effectAllowed).toBe('copyMove');
  });

  it('does not accept stale workspace state without a matching transfer marker', () => {
    const sourceTransfer = makeDataTransfer();
    setDraggedWorkspaceFile(sourceTransfer, {
      workspaceId: 'workspace-1',
      targetPaths: ['/repo/src/index.ts'],
    });

    const unrelatedTransfer = makeDataTransfer();

    expect(hasDraggedWorkspaceFile(unrelatedTransfer)).toBe(false);
    expect(getDraggedWorkspaceFile(unrelatedTransfer)).toBeNull();
    clearDraggedWorkspaceFile();
  });

  it('falls back to the serialized transfer payload after dragend clears same-window state', () => {
    const dataTransfer = makeDataTransfer();
    setDraggedWorkspaceFile(dataTransfer, {
      workspaceId: 'workspace-1',
      targetPaths: ['/repo/src/index.ts'],
    });
    clearDraggedWorkspaceFile();

    expect(getDraggedWorkspaceFile(dataTransfer)).toEqual({
      workspaceId: 'workspace-1',
      targetPaths: ['/repo/src/index.ts'],
    });
  });
});
