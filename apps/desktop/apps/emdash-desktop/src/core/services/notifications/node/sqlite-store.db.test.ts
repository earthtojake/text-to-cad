import { openFixture } from '@tooling/utils/db';
import { afterEach, describe, expect, it } from 'vitest';
import type { AppNotification } from '../api';
import { SqliteNotificationStore } from './sqlite-store';

const notification: AppNotification = {
  id: 'n-1',
  kind: 'agent-attention',
  groupKey: 'conversation:conv-1',
  title: 'Codex - Task',
  body: 'Your agent is waiting for input',
  target: { kind: 'task', projectId: 'project-1', taskId: 'task-1', conversationId: 'conv-1' },
  source: {
    kind: 'conversation',
    projectId: 'project-1',
    taskId: 'task-1',
    conversationId: 'conv-1',
  },
  sound: 'needs_attention',
  count: 1,
  createdAt: 1_000,
  readAt: null,
};

describe('SqliteNotificationStore', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  afterEach(() => {
    fixture?.close();
  });

  it('round-trips notifications and read state', async () => {
    fixture = await openFixture('empty');
    const store = new SqliteNotificationStore(fixture.db);

    expect(await store.insert(notification)).toEqual({ success: true, data: undefined });
    expect(await store.loadRecent({ since: 0, maxRows: 10 })).toEqual([notification]);

    expect(await store.markRead(['n-1'], 2_000)).toEqual({ success: true, data: undefined });
    expect(await store.loadRecent({ since: 0, maxRows: 10 })).toEqual([
      { ...notification, readAt: 2_000 },
    ]);

    expect(await store.remove(['n-1'])).toEqual({ success: true, data: undefined });
    expect(await store.loadRecent({ since: 0, maxRows: 10 })).toEqual([]);
  });
});
