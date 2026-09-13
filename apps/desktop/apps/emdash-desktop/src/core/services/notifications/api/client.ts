import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { notificationsContract, notificationsDomain } from './contract';

export type NotificationsClient = ContractClient<typeof notificationsContract>;

export function getNotificationsClient(): Promise<NotificationsClient> {
  return domainClient<NotificationsClient>(notificationsDomain, notificationsContract);
}
