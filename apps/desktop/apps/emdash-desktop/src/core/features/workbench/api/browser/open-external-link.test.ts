import { beforeEach, describe, expect, it, vi } from 'vitest';
import { confirmOpenExternalLink } from './open-external-link';

const mocks = vi.hoisted(() => ({
  clipboardWriteText: vi.fn(),
  getTaskComposition: vi.fn(),
  navigationRef: {
    viewId: 'home',
    params: {} as { projectId?: string; taskId?: string },
    key: 'home',
  },
  openExternal: vi.fn(),
  openModal: vi.fn(),
  toast: Object.assign(vi.fn(), { error: vi.fn() }),
}));

vi.mock('@core/features/workbench/api/browser/task-composition-selectors', () => ({
  getTaskComposition: mocks.getTaskComposition,
}));

vi.mock('@emdash/ui/react/primitives', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  toast: mocks.toast,
}));

vi.mock('@core/primitives/desktop-host/browser/host-client', () => ({
  copyTextToClipboard: mocks.clipboardWriteText,
  openExternal: mocks.openExternal,
}));

vi.mock('@core/manifests/browser/modal-api', () => ({
  openModal: mocks.openModal,
}));

vi.mock('@core/primitives/navigation/browser/navigation-selectors', () => ({
  getNavigation: () => ({
    currentViewId: 'home',
    currentRef: mocks.navigationRef,
  }),
}));

type ExternalLinkModalArgs = {
  url: string;
  onCopy: () => Promise<boolean>;
};

function getModalArgs(): ExternalLinkModalArgs {
  return mocks.openModal.mock.calls[0]?.[1] as ExternalLinkModalArgs;
}

describe('confirmOpenExternalLink', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.clipboardWriteText.mockResolvedValue({ success: true });
    mocks.navigationRef.viewId = 'home';
    mocks.navigationRef.params = {};
    mocks.openModal.mockResolvedValue({
      success: false,
      error: { type: 'modal_dismissed', reason: 'explicit' },
    });
  });

  it('copies the normalized link and reports success', async () => {
    confirmOpenExternalLink('https://example.com/docs).');

    const args = getModalArgs();
    expect(args.url).toBe('https://example.com/docs');

    await expect(args.onCopy()).resolves.toBe(true);

    expect(mocks.clipboardWriteText).toHaveBeenCalledWith('https://example.com/docs');
    expect(mocks.toast).toHaveBeenCalledWith('Link copied');
  });

  it('reports when the native clipboard write fails', async () => {
    mocks.clipboardWriteText.mockResolvedValue({ success: false, error: 'Clipboard unavailable' });

    confirmOpenExternalLink('https://example.com/docs');
    await expect(getModalArgs().onCopy()).resolves.toBe(false);

    expect(mocks.toast.error).toHaveBeenCalledWith('Copy failed', {
      description: 'The link could not be copied to the clipboard.',
    });
  });

  it('reports when the clipboard request rejects', async () => {
    mocks.clipboardWriteText.mockRejectedValue(new Error('IPC unavailable'));

    confirmOpenExternalLink('https://example.com/docs');

    await expect(getModalArgs().onCopy()).resolves.toBe(false);
    expect(mocks.toast.error).toHaveBeenCalledWith('Copy failed', {
      description: 'The link could not be copied to the clipboard.',
    });
  });

  it('opens the external browser after the modal completes with that choice', async () => {
    mocks.openModal.mockResolvedValue({
      success: true,
      data: 'external-browser',
    });
    mocks.openExternal.mockResolvedValue(undefined);

    confirmOpenExternalLink('https://example.com/docs');

    await vi.waitFor(() => {
      expect(mocks.openExternal).toHaveBeenCalledWith('https://example.com/docs');
    });
  });

  it('opens the link in the active Emdash task after that choice completes', async () => {
    const taskView = {
      paneLayout: { open: vi.fn() },
      setFocusedRegion: vi.fn(),
    };
    mocks.navigationRef.viewId = 'task';
    mocks.navigationRef.params = { projectId: 'project-1', taskId: 'task-1' };
    mocks.getTaskComposition.mockReturnValue(taskView);
    mocks.openModal.mockResolvedValue({
      success: true,
      data: 'emdash-browser',
    });

    confirmOpenExternalLink('https://example.com/docs');

    await vi.waitFor(() => {
      expect(taskView.paneLayout.open).toHaveBeenCalledWith('browser', {
        initialUrl: 'https://example.com/docs',
      });
      expect(taskView.setFocusedRegion).toHaveBeenCalledWith('main');
    });
  });

  it('does nothing when the modal is dismissed', async () => {
    confirmOpenExternalLink('https://example.com/docs');

    await Promise.resolve();

    expect(mocks.openExternal).not.toHaveBeenCalled();
  });
});
