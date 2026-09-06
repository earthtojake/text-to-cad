import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  appendWorkbenchChatReference,
  hasWorkbenchChatInputSubscriber,
  imageBytesFromDataUrl,
  publishWorkbenchChatInput,
  resetWorkbenchChatInputBridgeForTests,
  subscribeWorkbenchChatInput,
} from './workbench-chat-input-bridge';

afterEach(resetWorkbenchChatInputBridgeForTests);

describe('workbench chat input bridge', () => {
  it('delivers CAD input only to the matching task composer', async () => {
    const first = vi.fn(() => true);
    const second = vi.fn(() => true);
    subscribeWorkbenchChatInput({ projectId: 'project', taskId: 'first' }, first);
    subscribeWorkbenchChatInput({ projectId: 'project', taskId: 'second' }, second);

    expect(hasWorkbenchChatInputSubscriber({ projectId: 'project', taskId: 'second' })).toBe(true);

    const delivered = await publishWorkbenchChatInput(
      { projectId: 'project', taskId: 'second' },
      { kind: 'reference', reference: '#o1.1.f5' }
    );

    expect(delivered).toBe(true);
    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledWith({ kind: 'reference', reference: '#o1.1.f5' });
  });

  it('uses the visible composer first and falls back when it declines the input', async () => {
    const older = vi.fn(() => true);
    const visible = vi.fn(() => false);
    subscribeWorkbenchChatInput({ projectId: 'project', taskId: 'task' }, older);
    subscribeWorkbenchChatInput({ projectId: 'project', taskId: 'task' }, visible);

    const delivered = await publishWorkbenchChatInput(
      { projectId: 'project', taskId: 'task' },
      {
        kind: 'image',
        dataUrl: 'data:image/png;base64,AQID',
        mimeType: 'image/png',
        name: 'cad-annotation.png',
      }
    );

    expect(delivered).toBe(true);
    expect(visible).toHaveBeenCalledOnce();
    expect(older).toHaveBeenCalledOnce();
  });

  it('stops delivering after the composer unmounts', async () => {
    const handler = vi.fn(() => true);
    const unsubscribe = subscribeWorkbenchChatInput(
      { projectId: 'project', taskId: 'task' },
      handler
    );
    unsubscribe();

    expect(hasWorkbenchChatInputSubscriber({ projectId: 'project', taskId: 'task' })).toBe(false);

    expect(
      await publishWorkbenchChatInput(
        { projectId: 'project', taskId: 'task' },
        { kind: 'reference', reference: '#o1.1.e2' }
      )
    ).toBe(false);
    expect(handler).not.toHaveBeenCalled();
  });

  it('appends an exact viewer reference once without overwriting the draft', () => {
    expect(appendWorkbenchChatReference('Increase this hole', '#o1.1.f5')).toBe(
      'Increase this hole #o1.1.f5 '
    );
    expect(appendWorkbenchChatReference('Inspect #o1.1.f5 ', '#o1.1.f5')).toBe('Inspect #o1.1.f5 ');
  });

  it('decodes the PNG screenshot before the ACP upload', () => {
    expect(imageBytesFromDataUrl('data:image/png;base64,AQID', 'image/png')).toEqual(
      Uint8Array.from([1, 2, 3])
    );
    expect(imageBytesFromDataUrl('data:image/jpeg;base64,AQID', 'image/png')).toBeNull();
    expect(imageBytesFromDataUrl('data:image/png;base64,***', 'image/png')).toBeNull();
  });
});
