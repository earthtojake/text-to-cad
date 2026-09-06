import { describe, expect, it, vi } from 'vitest';
import { captureCadScreenshotForWorkbenchChat } from './cad-workbench-chat-workflow';

describe('CAD workbench chat workflow', () => {
  it('captures an annotated viewport and delivers it to the matching workbench chat', async () => {
    const capture = vi.fn(async () => ({
      success: true as const,
      dataUrl: 'data:image/png;base64,AQID',
    }));
    const publish = vi.fn(async () => true);

    const result = await captureCadScreenshotForWorkbenchChat({
      target: { projectId: 'project', taskId: 'task' },
      capture,
      publish,
      name: 'annotated-model.png',
    });

    expect(result).toEqual({ success: true });
    expect(capture).toHaveBeenCalledOnce();
    expect(publish).toHaveBeenCalledWith(
      { projectId: 'project', taskId: 'task' },
      {
        kind: 'image',
        dataUrl: 'data:image/png;base64,AQID',
        mimeType: 'image/png',
        name: 'annotated-model.png',
      }
    );
  });

  it('does not publish a missing viewport capture', async () => {
    const publish = vi.fn(async () => true);

    const result = await captureCadScreenshotForWorkbenchChat({
      target: { projectId: 'project', taskId: 'task' },
      capture: async () => ({ success: false, error: 'CAD viewport is not ready.' }),
      publish,
    });

    expect(result).toEqual({ success: false, error: 'CAD viewport is not ready.' });
    expect(publish).not.toHaveBeenCalled();
  });
});
