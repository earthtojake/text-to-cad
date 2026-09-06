import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  canOpenBrowserUrlExternally,
  captureBrowserScreenshot,
  clearBrowserData,
  confirmClearBrowserStorage,
  openBrowserUrlExternally,
} from './browser-toolbar-actions';

const mocks = vi.hoisted(() => ({
  captureScreenshot: vi.fn(),
  clearData: vi.fn(),
  openExternal: vi.fn(),
  openModal: vi.fn(),
  reload: vi.fn(),
  reloadIgnoringCache: vi.fn(),
  toast: Object.assign(vi.fn(), { error: vi.fn() }),
}));

vi.mock('@core/primitives/desktop-host/browser/host-client', () => ({
  openExternal: mocks.openExternal,
}));

vi.mock('@core/features/browser/api/browser/client', () => ({
  getBrowserClient: vi.fn(async () => ({
    captureScreenshot: mocks.captureScreenshot,
    clearData: mocks.clearData,
  })),
}));

vi.mock('@core/manifests/browser/modal-api', () => ({
  openModal: mocks.openModal,
}));

vi.mock('@emdash/ui/react/primitives', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  toast: mocks.toast,
}));

function session() {
  return {
    browserId: 'browser-1',
    projectId: 'project-1',
    workspaceId: 'workspace-1',
    taskId: 'task-1',
    profileId: 'default',
    partition: 'persist:emdash-browser-profile',
    currentUrl: 'https://example.com/',
    title: 'Example',
    isLoading: false,
    canGoBack: false,
    canGoForward: false,
    zoomFactor: 1,
    createdAt: 1,
    updatedAt: 1,
  };
}

describe('browser toolbar actions', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.captureScreenshot.mockResolvedValue({ success: true });
    mocks.clearData.mockResolvedValue({ success: true });
    mocks.openModal.mockResolvedValue({
      success: false,
      error: { type: 'modal_dismissed', reason: 'explicit' },
    });
  });

  it('opens only http and https URLs externally', () => {
    openBrowserUrlExternally('example.com');
    openBrowserUrlExternally('javascript:alert(1)');
    openBrowserUrlExternally('about:blank');

    expect(mocks.openExternal).toHaveBeenCalledTimes(1);
    expect(mocks.openExternal).toHaveBeenCalledWith('https://example.com/');
  });

  it('reports whether the current URL can be opened externally', () => {
    expect(canOpenBrowserUrlExternally('https://example.com/')).toBe(true);
    expect(canOpenBrowserUrlExternally('localhost:3000')).toBe(true);
    expect(canOpenBrowserUrlExternally('about:blank')).toBe(false);
    expect(canOpenBrowserUrlExternally('javascript:alert(1)')).toBe(false);
  });

  it('captures screenshots and shows feedback on success', async () => {
    await captureBrowserScreenshot(session());

    expect(mocks.captureScreenshot).toHaveBeenCalledWith({ browserId: 'browser-1' });
    expect(mocks.toast).toHaveBeenCalledWith('Screenshot copied to clipboard');
  });

  it('shows feedback when screenshot capture fails', async () => {
    mocks.captureScreenshot.mockResolvedValue({ success: false });
    await captureBrowserScreenshot(session());

    expect(mocks.captureScreenshot).toHaveBeenCalledWith({ browserId: 'browser-1' });
    expect(mocks.toast.error).toHaveBeenCalledWith('Could not capture screenshot');
  });

  it('clears storage only after explicit modal confirmation and reloads on success', async () => {
    mocks.openModal.mockResolvedValueOnce({ success: true, data: undefined });
    confirmClearBrowserStorage(session(), { reload: mocks.reload } as never);

    expect(mocks.openModal).toHaveBeenCalledWith(
      'confirmActionModal',
      expect.objectContaining({
        title: 'Clear browser storage?',
        variant: 'destructive',
      })
    );

    await vi.waitFor(() => {
      expect(mocks.clearData).toHaveBeenCalledWith({
        browserId: 'browser-1',
        kind: 'storage',
      });
      expect(mocks.reload).toHaveBeenCalledWith();
    });
  });

  it('does not clear storage when the confirmation modal is dismissed', async () => {
    confirmClearBrowserStorage(session(), { reload: mocks.reload } as never);

    await vi.waitFor(() => expect(mocks.openModal).toHaveBeenCalled());
    expect(mocks.clearData).not.toHaveBeenCalled();
    expect(mocks.reload).not.toHaveBeenCalled();
  });

  it('clears cookies and reloads on success', async () => {
    await clearBrowserData(session(), 'cookies', mocks.reload);

    expect(mocks.clearData).toHaveBeenCalledWith({ browserId: 'browser-1', kind: 'cookies' });
    expect(mocks.reload).toHaveBeenCalledWith();
  });

  it('clears the cache and force-reloads on success', async () => {
    await clearBrowserData(session(), 'cache', mocks.reloadIgnoringCache);

    expect(mocks.clearData).toHaveBeenCalledWith({ browserId: 'browser-1', kind: 'cache' });
    expect(mocks.reloadIgnoringCache).toHaveBeenCalledWith();
  });

  it('does not reload and shows feedback when clearing cookies fails', async () => {
    mocks.clearData.mockResolvedValue({ success: false });
    await clearBrowserData(session(), 'cookies', mocks.reload);

    expect(mocks.clearData).toHaveBeenCalledWith({ browserId: 'browser-1', kind: 'cookies' });
    expect(mocks.reload).not.toHaveBeenCalled();
    expect(mocks.toast.error).toHaveBeenCalledWith('Could not clear browser data', {
      description: 'Try again, or reload the browser view manually.',
    });
  });

  it('does not reload and shows feedback when clearing browser data rejects', async () => {
    const error = new Error('IPC failed');
    mocks.clearData.mockRejectedValue(error);
    await clearBrowserData(session(), 'cache', mocks.reloadIgnoringCache);

    expect(mocks.clearData).toHaveBeenCalledWith({ browserId: 'browser-1', kind: 'cache' });
    expect(mocks.reloadIgnoringCache).not.toHaveBeenCalled();
    expect(mocks.toast.error).toHaveBeenCalledWith('Could not clear browser data', {
      description: 'IPC failed',
    });
  });
});
