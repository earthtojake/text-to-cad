import { createScope, type Scope } from '@emdash/shared/concurrency';
import {
  observe,
  optimistic,
  remote,
  whenReady,
  type OptimisticView,
  type RemoteModel,
} from '@emdash/wire/state';
import { computed, makeObservable, observable, runInAction } from 'mobx';
import {
  getNotificationsClient,
  type NotificationsClient,
} from '@core/services/notifications/api/client';
import {
  notificationsContract,
  reduceDismiss,
  reduceMarkAllRead,
  reduceMarkRead,
  type AppNotification,
  type NotificationList,
} from '../api';

type FeedRemote = RemoteModel<typeof notificationsContract.feed>;
type FeedMember = ReturnType<FeedRemote>;

export class NotificationsFeedStore {
  private readonly scope: Scope;
  private readonly remoteModel: FeedRemote;
  private readonly member: FeedMember;
  private readonly view: OptimisticView<NotificationList>;
  private readonly readyPromise: Promise<void>;
  private list: NotificationList = {};

  constructor(client: NotificationsClient) {
    this.scope = createScope({ label: 'notifications-feed-store' });
    this.remoteModel = remote(notificationsContract.feed, client.feed, {
      scope: this.scope,
      lingerMs: 15_000,
    });
    this.member = this.remoteModel(undefined);
    this.view = optimistic(this.member.states.list);
    makeObservable<NotificationsFeedStore, 'list'>(this, {
      list: observable.ref,
      all: computed,
      unreadCount: computed,
    });
    observe(
      this.view,
      (snapshot) => {
        runInAction(() => {
          this.list = snapshot.value ?? {};
        });
      },
      { scope: this.scope }
    );
    this.readyPromise = whenReady(this.view, { scope: this.scope }).then(() => undefined);
  }

  get ready(): Promise<void> {
    return this.readyPromise;
  }

  get all(): AppNotification[] {
    return Object.values(this.list).sort((a, b) => b.createdAt - a.createdAt);
  }

  get unreadCount(): number {
    return this.all.reduce(
      (sum, notification) => (notification.readAt === null ? sum + notification.count : sum),
      0
    );
  }

  read(ids: string[]): void {
    if (ids.length === 0) return;
    void this.view.run(this.member.mutations.markRead, { ids, at: Date.now() }, reduceMarkRead);
  }

  markAllRead(): void {
    void this.view.run(this.member.mutations.markAllRead, { at: Date.now() }, reduceMarkAllRead);
  }

  dismiss(id: string): void {
    void this.view.run(this.member.mutations.dismiss, { ids: [id] }, reduceDismiss);
  }

  async dispose(): Promise<void> {
    await this.scope.dispose();
  }
}

let storePromise: Promise<NotificationsFeedStore> | null = null;

export function getNotificationsFeedStore(): Promise<NotificationsFeedStore> {
  storePromise ??= getNotificationsClient().then((client) => {
    const store = new NotificationsFeedStore(client);
    return store.ready.then(() => store);
  });
  return storePromise;
}

export async function resetNotificationsFeedStoreForTests(): Promise<void> {
  const store = await storePromise;
  storePromise = null;
  await store?.dispose();
}
