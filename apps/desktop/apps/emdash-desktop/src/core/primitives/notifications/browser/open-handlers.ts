export type NotificationOpenTarget =
  | {
      kind: 'task';
      projectId: string;
      taskId: string;
      conversationId?: string;
    }
  | { kind: 'update'; version?: string }
  | { kind: 'none' };

type NotificationOpenHandler<T extends NotificationOpenTarget = NotificationOpenTarget> = (
  target: T,
  notificationId: string
) => void | Promise<void>;

const handlers = new Map<NotificationOpenTarget['kind'], NotificationOpenHandler>();

export function registerNotificationOpenHandler<K extends NotificationOpenTarget['kind']>(
  kind: K,
  handler: NotificationOpenHandler<Extract<NotificationOpenTarget, { kind: K }>>
): () => void {
  handlers.set(kind, handler as NotificationOpenHandler);
  return () => {
    if (handlers.get(kind) === handler) handlers.delete(kind);
  };
}

export function runNotificationOpenHandler(
  target: NotificationOpenTarget,
  notificationId: string
): void {
  void handlers.get(target.kind)?.(target, notificationId);
}
