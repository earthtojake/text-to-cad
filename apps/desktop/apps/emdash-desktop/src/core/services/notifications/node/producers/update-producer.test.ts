import { describe, expect, it, vi } from 'vitest';
import {
  publishUpdateAvailableNotification,
  publishUpdateDownloadedNotification,
  publishUpdateErrorNotification,
} from './update-producer';

describe('update notification producer', () => {
  it('publishes available updates with version dedupe', () => {
    const service = { publish: vi.fn(() => 'n-0') };

    expect(publishUpdateAvailableNotification(service, '1.2.3')).toBe('n-0');
    expect(service.publish).toHaveBeenCalledWith({
      kind: 'update-available',
      groupKey: 'app-update',
      dedupeKey: 'update-available:1.2.3',
      title: 'Update available',
      body: 'Hardcore 1.2.3 is ready to download.',
      sound: null,
      target: { kind: 'update', version: '1.2.3' },
      source: { kind: 'app' },
    });
  });

  it('publishes downloaded updates with version dedupe', () => {
    const service = { publish: vi.fn(() => 'n-1') };

    expect(publishUpdateDownloadedNotification(service, '1.2.3')).toBe('n-1');
    expect(service.publish).toHaveBeenCalledWith({
      kind: 'update-downloaded',
      groupKey: 'app-update',
      dedupeKey: 'update:1.2.3',
      title: 'Update ready',
      body: 'Hardcore 1.2.3 has been downloaded and will install on restart.',
      sound: null,
      target: { kind: 'update', version: '1.2.3' },
      source: { kind: 'app' },
    });
  });

  it('publishes update errors as feed-only notifications', () => {
    const service = { publish: vi.fn(() => 'n-2') };

    expect(publishUpdateErrorNotification(service, 'Network failed')).toBe('n-2');
    expect(service.publish).toHaveBeenCalledWith({
      kind: 'update-error',
      groupKey: 'app-update',
      dedupeKey: 'update-error:Network failed',
      title: 'Update failed',
      body: 'Network failed',
      sound: null,
      target: { kind: 'update' },
      source: { kind: 'app' },
    });
  });
});
