import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { openWithOS } from './open-with-os';

const mocks = vi.hoisted(() => ({
  openPath: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('@core/primitives/desktop-host/browser/host-client', () => ({
  getHostClient: async () => ({ openPath: mocks.openPath }),
}));

vi.mock('@emdash/ui/react/primitives', () => ({
  toast: { error: mocks.toastError },
}));

describe('openWithOS', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.openPath.mockResolvedValue({ success: true });
  });

  it('opens a raw path with the OS default application', async () => {
    await openWithOS('/tmp/report.pdf');

    expect(mocks.openPath).toHaveBeenCalledWith({ path: '/tmp/report.pdf' });
    expect(mocks.toastError).not.toHaveBeenCalled();
  });

  it('opens a HostFileRef by its native path', async () => {
    await openWithOS(hostFileRefFromNativePath('/tmp/photo.png'));

    expect(mocks.openPath).toHaveBeenCalledWith({ path: '/tmp/photo.png' });
  });

  it('surfaces an OS-open failure as a toast', async () => {
    mocks.openPath.mockResolvedValue({ success: false, error: 'no handler' });

    await openWithOS('/tmp/strange.bin');

    expect(mocks.toastError).toHaveBeenCalledWith('Could not open /tmp/strange.bin: no handler');
  });
});
