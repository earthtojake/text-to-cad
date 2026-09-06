import {
  publishUpdateAvailableNotification,
  publishUpdateDownloadedNotification,
  publishUpdateErrorNotification,
  type NotificationService,
} from '@core/services/notifications/node';
import { updateService } from './update-service';

export function installUpdateNotifications(notificationService: NotificationService): void {
  updateService.setNotificationPublisher({
    available: (version) => {
      publishUpdateAvailableNotification(notificationService, version);
    },
    downloaded: (version) => {
      publishUpdateDownloadedNotification(notificationService, version);
    },
    error: (message) => {
      publishUpdateErrorNotification(notificationService, message);
    },
  });
}
