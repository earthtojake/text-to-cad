import type { NotificationList } from './schemas';

export type MarkReadInput = {
  ids: string[];
  at: number;
};

export type MarkAllReadInput = {
  at: number;
};

export type DismissInput = {
  ids: string[];
};

export function reduceMarkRead(list: NotificationList, input: MarkReadInput): void {
  for (const id of input.ids) {
    if (list[id]) list[id].readAt ??= input.at;
  }
}

export function reduceMarkAllRead(list: NotificationList, input: MarkAllReadInput): void {
  for (const notification of Object.values(list)) {
    notification.readAt ??= input.at;
  }
}

export function reduceDismiss(list: NotificationList, input: DismissInput): void {
  for (const id of input.ids) delete list[id];
}
