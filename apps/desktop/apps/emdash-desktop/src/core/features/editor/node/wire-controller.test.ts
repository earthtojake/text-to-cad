import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { encodeResourceUri, hostFileRef, parseAbsolute } from '@emdash/core/primitives/path/api';
import { describe, expect, it, vi } from 'vitest';
import { createEditorWireController } from './wire-controller';

const uri = resourceUri('/repo/worktree/src/index.ts');
const rootUri = resourceUri('/repo/worktree');

describe('createEditorWireController', () => {
  it('forwards buffer procedures to the crash-recovery store', async () => {
    const editorBuffer = {
      saveBuffer: vi.fn(async () => undefined),
      clearBuffer: vi.fn(async () => undefined),
      listBuffers: vi.fn(async () => [{ uri, content: 'recovered' }]),
    };
    const controller = createEditorWireController({ editorBuffer: editorBuffer as never });

    await controller.call('saveBuffer', { uri, content: 'draft' });
    expect(editorBuffer.saveBuffer).toHaveBeenCalledWith(uri, 'draft');

    await controller.call('clearBuffer', { uri });
    expect(editorBuffer.clearBuffer).toHaveBeenCalledWith(uri);

    await expect(controller.call('listBuffers', { root: rootUri })).resolves.toEqual([
      { uri, content: 'recovered' },
    ]);
    expect(editorBuffer.listBuffers).toHaveBeenCalledWith(rootUri);

    await controller.call('listBuffers', {});
    expect(editorBuffer.listBuffers).toHaveBeenLastCalledWith(undefined);
  });
});

function resourceUri(path: string) {
  const parsed = parseAbsolute(path, { profile: { style: 'posix' } });
  if (!parsed.success) throw new Error(parsed.error.message);
  return encodeResourceUri(hostFileRef(LOCAL_HOST_REF, parsed.data));
}
