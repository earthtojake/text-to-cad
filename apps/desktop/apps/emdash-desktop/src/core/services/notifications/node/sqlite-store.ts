import { err, ok, type Result } from '@emdash/shared';
import { desc, gte, inArray, lt } from 'drizzle-orm';
import type { AppDb } from '@core/services/app-db/node/db';
import { notifications } from '@core/services/app-db/node/schema';
import type { AppNotification } from '../api';
import type { NotificationStore } from '../api/ports';

export class SqliteNotificationStore implements NotificationStore {
  constructor(private readonly db: AppDb) {}

  async loadRecent(options: { maxRows: number; since: number }): Promise<AppNotification[]> {
    const rows = await this.db
      .select()
      .from(notifications)
      .where(gte(notifications.createdAt, options.since))
      .orderBy(desc(notifications.createdAt))
      .limit(options.maxRows);

    return rows
      .flatMap((row): AppNotification[] => {
        if (!row.payload) return [];
        return [
          {
            id: row.id,
            kind: row.kind,
            groupKey: row.groupKey,
            title: row.title,
            body: row.body,
            target: row.payload.target,
            source: row.payload.source,
            sound: row.payload.sound,
            count: row.count,
            createdAt: row.createdAt,
            readAt: row.readAt,
          },
        ];
      })
      .sort((a, b) => a.createdAt - b.createdAt);
  }

  async insert(notification: AppNotification): Promise<Result<void, string>> {
    try {
      await this.db
        .insert(notifications)
        .values({
          id: notification.id,
          kind: notification.kind,
          groupKey: notification.groupKey,
          title: notification.title,
          body: notification.body,
          payload: {
            version: '1',
            target: notification.target,
            source: notification.source,
            sound: notification.sound,
          },
          count: notification.count,
          createdAt: notification.createdAt,
          readAt: notification.readAt,
        })
        .onConflictDoUpdate({
          target: notifications.id,
          set: {
            kind: notification.kind,
            groupKey: notification.groupKey,
            title: notification.title,
            body: notification.body,
            payload: {
              version: '1',
              target: notification.target,
              source: notification.source,
              sound: notification.sound,
            },
            count: notification.count,
            createdAt: notification.createdAt,
            readAt: notification.readAt,
          },
        });
      return ok<void>();
    } catch (error) {
      return err(error instanceof Error ? error.message : String(error));
    }
  }

  async markRead(ids: string[], at: number): Promise<Result<void, string>> {
    if (ids.length === 0) return ok<void>();
    try {
      await this.db.update(notifications).set({ readAt: at }).where(inArray(notifications.id, ids));
      return ok<void>();
    } catch (error) {
      return err(error instanceof Error ? error.message : String(error));
    }
  }

  async markAllRead(at: number): Promise<Result<void, string>> {
    try {
      await this.db.update(notifications).set({ readAt: at });
      return ok<void>();
    } catch (error) {
      return err(error instanceof Error ? error.message : String(error));
    }
  }

  async remove(ids: string[]): Promise<Result<void, string>> {
    if (ids.length === 0) return ok<void>();
    try {
      await this.db.delete(notifications).where(inArray(notifications.id, ids));
      return ok<void>();
    } catch (error) {
      return err(error instanceof Error ? error.message : String(error));
    }
  }

  async prune(options: { olderThan: number; maxRows: number }): Promise<Result<void, string>> {
    try {
      await this.db.delete(notifications).where(lt(notifications.createdAt, options.olderThan));

      const overflow = await this.db
        .select({ id: notifications.id })
        .from(notifications)
        .orderBy(desc(notifications.createdAt))
        .offset(options.maxRows);
      await this.remove(overflow.map((row) => row.id));
      return ok<void>();
    } catch (error) {
      return err(error instanceof Error ? error.message : String(error));
    }
  }
}
