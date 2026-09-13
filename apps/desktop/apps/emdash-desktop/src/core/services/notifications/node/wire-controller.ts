import { createController, type Controller } from '@emdash/wire/rpc';
import { notificationsContract } from '../api';
import type { NotificationService } from './notification-service';

export function createNotificationsWireController(service: NotificationService): Controller {
  return createController(notificationsContract, {
    feed: service.feedHost(),
    delivery: service.deliveryHost(),
  });
}
