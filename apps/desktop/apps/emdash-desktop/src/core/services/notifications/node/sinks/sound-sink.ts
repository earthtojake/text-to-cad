import type { EmitNotificationDelivery, NotificationSink } from '../../api/ports';

export function createSoundNotificationSink(
  emitDelivery: EmitNotificationDelivery
): NotificationSink {
  return {
    id: 'sound',
    deliver({ notification }) {
      if (!notification.sound) return;
      emitDelivery({
        type: 'sound',
        sound: notification.sound,
        notificationId: notification.id,
      });
    },
  };
}
