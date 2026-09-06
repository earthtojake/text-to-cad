import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { err, ok, type Result } from '@emdash/shared';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import {
  executeConversationRemoval,
  tombstoneConversationForRemoval,
  type ConversationRemovalBroker,
} from './conversation-removal';

describe('tombstoneConversationForRemoval', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  function seedConversation(id: string): void {
    createConversationRegistry(fixture.db).adopt({
      id,
      title: `Conversation ${id}`,
      provider: 'claude',
      type: 'acp',
      location: 'local',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
  }

  it('writes the frozen tombstone atomically; the row stays live as the pending state', () => {
    seedConversation('conv-1');

    const written = fixture.db.transaction((tx) =>
      tombstoneConversationForRemoval(tx, { conversationId: 'conv-1', createdAt: 1_000 })
    );

    expect(written.outcome).toBe('tombstoned');
    const row = createConversationRegistry(fixture.db).getLive('conv-1');
    expect(row?.deletionTombstone).toEqual({
      version: '1',
      targetRecordId: 'conv-1',
      tombstonedAt: 1_000,
    });
  });

  it('suppresses duplicates without overwriting the first write', () => {
    seedConversation('conv-2');
    fixture.db.transaction((tx) =>
      tombstoneConversationForRemoval(tx, { conversationId: 'conv-2', createdAt: 1_000 })
    );

    const second = fixture.db.transaction((tx) =>
      tombstoneConversationForRemoval(tx, { conversationId: 'conv-2', createdAt: 2_000 })
    );

    expect(second.outcome).toBe('duplicate');
    expect(
      createConversationRegistry(fixture.db).getLive('conv-2')?.deletionTombstone
    ).toMatchObject({ tombstonedAt: 1_000 });
  });

  it('treats absent and untracked rows as duplicates (nothing to mark)', () => {
    const absent = fixture.db.transaction((tx) =>
      tombstoneConversationForRemoval(tx, { conversationId: 'conv-missing', createdAt: 1_000 })
    );
    expect(absent.outcome).toBe('duplicate');

    seedConversation('conv-3');
    createConversationRegistry(fixture.db).untrack(['conv-3'], '2026-01-01T00:00:00.000Z');
    const untracked = fixture.db.transaction((tx) =>
      tombstoneConversationForRemoval(tx, { conversationId: 'conv-3', createdAt: 1_000 })
    );
    expect(untracked.outcome).toBe('duplicate');
  });
});

describe('executeConversationRemoval', () => {
  type SessionKillMock = Mock<(input: { conversationId: string }) => Promise<unknown>>;
  type IndexDeleteMock = Mock<
    (input: { conversationId: string }) => Promise<Result<void, { type: string; message?: string }>>
  >;

  function fakeBroker(overrides: {
    reachable?: boolean;
    killAcp?: SessionKillMock;
    deleteTui?: SessionKillMock;
    deleteRecord?: IndexDeleteMock;
    deleteAttachments?: SessionKillMock;
  }) {
    const calls: string[] = [];
    const killAcp: SessionKillMock =
      overrides.killAcp ??
      vi.fn(async () => {
        calls.push('acp.kill');
        return ok(undefined);
      });
    const deleteTui: SessionKillMock =
      overrides.deleteTui ??
      vi.fn(async () => {
        calls.push('tuiAgents.delete');
        return ok(undefined);
      });
    const deleteRecord: IndexDeleteMock =
      overrides.deleteRecord ??
      vi.fn(async () => {
        calls.push('conversations.delete');
        return ok(undefined);
      });
    const deleteAttachments: SessionKillMock =
      overrides.deleteAttachments ??
      vi.fn(async () => {
        calls.push('acp.deleteAttachments');
        return ok(undefined);
      });
    const broker: ConversationRemovalBroker = {
      client: async () =>
        (overrides.reachable ?? true)
          ? ok({
              acp: { kill: killAcp, deleteAttachments },
              tuiAgents: { delete: deleteTui },
              conversations: { delete: deleteRecord },
            })
          : err({ type: 'ssh-connection-failed', message: 'down' }),
    };
    return { broker, calls, killAcp, deleteTui, deleteRecord, deleteAttachments };
  }

  it('kills both session surfaces before deleting the index record', async () => {
    const host = fakeBroker({});

    const outcome = await executeConversationRemoval(host.broker, LOCAL_HOST_REF, 'conv-1');

    expect(outcome).toBe('ok');
    // Session kill is part of the verb (spec §4.3) — strictly ordered before the delete;
    // attachment cleanup (spec §3.6) follows the successful index delete.
    expect(host.calls).toEqual([
      'acp.kill',
      'tuiAgents.delete',
      'conversations.delete',
      'acp.deleteAttachments',
    ]);
    expect(host.killAcp).toHaveBeenCalledWith({ conversationId: 'conv-1' });
    expect(host.deleteTui).toHaveBeenCalledWith({ conversationId: 'conv-1' });
    expect(host.deleteRecord).toHaveBeenCalledWith({ conversationId: 'conv-1' });
    expect(host.deleteAttachments).toHaveBeenCalledWith({ conversationId: 'conv-1' });
  });

  it('deletes the record even when session kills fail', async () => {
    const host = fakeBroker({
      killAcp: vi.fn(async () => {
        throw new Error('acp runtime crashed');
      }),
      deleteTui: vi.fn(async () => {
        throw new Error('tui runtime crashed');
      }),
    });

    const outcome = await executeConversationRemoval(host.broker, LOCAL_HOST_REF, 'conv-1');

    expect(outcome).toBe('ok');
    expect(host.deleteRecord).toHaveBeenCalledWith({ conversationId: 'conv-1' });
  });

  it('reports unreachable when the broker cannot resolve the host', async () => {
    const host = fakeBroker({ reachable: false });

    const outcome = await executeConversationRemoval(host.broker, LOCAL_HOST_REF, 'conv-1');

    expect(outcome).toBe('unreachable');
    expect(host.deleteRecord).not.toHaveBeenCalled();
  });

  it('reports ok even when attachment cleanup fails after the record delete', async () => {
    const host = fakeBroker({
      deleteAttachments: vi.fn(async () => {
        throw new Error('acp runtime crashed');
      }),
    });

    const outcome = await executeConversationRemoval(host.broker, LOCAL_HOST_REF, 'conv-1');

    expect(outcome).toBe('ok');
    expect(host.deleteRecord).toHaveBeenCalledWith({ conversationId: 'conv-1' });
  });

  it('skips attachment cleanup when the index delete fails', async () => {
    const host = fakeBroker({
      deleteRecord: vi.fn(async () => err({ type: 'index-io-error', message: 'disk' })),
    });

    await executeConversationRemoval(host.broker, LOCAL_HOST_REF, 'conv-1');

    expect(host.deleteAttachments).not.toHaveBeenCalled();
  });

  it('classifies a mid-call unreachability error as unreachable, others as failed', async () => {
    const dropped = fakeBroker({
      deleteRecord: vi.fn(async () => err({ type: 'host-unreachable', message: 'gone' })),
    });
    await expect(
      executeConversationRemoval(dropped.broker, LOCAL_HOST_REF, 'conv-1')
    ).resolves.toBe('unreachable');

    const failed = fakeBroker({
      deleteRecord: vi.fn(async () => err({ type: 'index-io-error', message: 'disk' })),
    });
    await expect(
      executeConversationRemoval(failed.broker, LOCAL_HOST_REF, 'conv-1')
    ).resolves.toEqual({
      failed: { class: 'transient', stage: 'remove', message: 'disk' },
    });
  });
});
