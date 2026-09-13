import type { NotificationService } from '../notification-service';

export function publishUpdateAvailableNotification(
  service: Pick<NotificationService, 'publish'>,
  version: string
): string {
  return service.publish({
    kind: 'update-available',
    groupKey: 'app-update',
    dedupeKey: `update-available:${version}`,
    title: 'Update available',
    body: `Hardcore ${version} is ready to download.`,
    sound: null,
    target: { kind: 'update', version },
    source: { kind: 'app' },
  });
}

export function publishUpdateDownloadedNotification(
  service: Pick<NotificationService, 'publish'>,
  version: string
): string {
  return service.publish({
    kind: 'update-downloaded',
    groupKey: 'app-update',
    dedupeKey: `update:${version}`,
    title: 'Update ready',
    body: `Hardcore ${version} has been downloaded and will install on restart.`,
    sound: null,
    target: { kind: 'update', version },
    source: { kind: 'app' },
  });
}

export function publishUpdateErrorNotification(
  service: Pick<NotificationService, 'publish'>,
  message: string
): string {
  return service.publish({
    kind: 'update-error',
    groupKey: 'app-update',
    dedupeKey: `update-error:${message}`,
    title: 'Update failed',
    body: message,
    sound: null,
    target: { kind: 'update' },
    source: { kind: 'app' },
  });
}
