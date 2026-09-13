import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import {
  conversationsContract,
  type ConversationRecord,
  type ConversationRecords,
} from '@emdash/core/runtimes/conversations/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { createController } from '@emdash/wire/rpc';
import { cell, expose, type Cell } from '@emdash/wire/state';
import { createTestWire, type TestWire } from '@emdash/wire/testing';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import { ConversationSyncService } from './conversation-sync-service';

function hostRecord(
  overrides: Partial<ConversationRecord> & { conversationId: string }
): ConversationRecord {
  return {
    provider: 'claude-code',
    type: 'acp',
    cwd: '/work/repo',
    workspacePath: '/work/repo',
    idRegime: 'emdash-chosen',
    createdAt: Date.parse('2026-01-01T00:00:00.000Z'),
    title: 'Host truth',
    config: { model: 'sonnet' },
    providerSessionId: null,
    providerSessionIdObservedAt: null,
    lastSessionActivityAt: null,
    lastSpawnedAt: null,
    lastResumeOutcome: 'never-resumed',
    updatedAt: Date.parse('2026-01-02T00:00:00.000Z'),
    ...overrides,
  };
}

/**
 * End-to-end convergence: a fake host serves the `records` live model over a test wire
 * (the same `expose`-over-a-cell shape the real runtime uses), and the sync service
 * converges the client registry (real SQLite) toward it. The cache is never the
 * authority (`conv.cache-not-authority`); the subscription is the only thing that
 * moves it. The mutation verbs are stubbed because the sync path never calls them.
 */
describe('ConversationSyncService', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;
  let hostRecords: Cell<ConversationRecords>;
  let recordsHost: ReturnType<typeof expose<typeof conversationsContract.records>>;
  let wire: TestWire<typeof conversationsContract>;
  let service: ConversationSyncService;
  let hostReachable: boolean;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    hostRecords = cell<ConversationRecords>({}, { name: 'test-conversation-records' });
    recordsHost = expose(conversationsContract.records, { list: () => hostRecords });
    const unused = () => {
      throw new Error('not exercised by the sync service');
    };
    wire = createTestWire(
      conversationsContract,
      createController(conversationsContract, {
        records: recordsHost,
        create: unused,
        rename: unused,
        updateConfig: unused,
        delete: unused,
        reports: {
          sessionStarted: unused,
          providerSessionId: unused,
          sessionActivity: unused,
          sessionEnded: unused,
        },
      })
    );
    hostReachable = true;
    const broker = {
      client: async () =>
        hostReachable
          ? { success: true, data: { conversations: wire.client } }
          : { success: false, error: { type: 'host-unavailable' } },
    } as unknown as RuntimeBroker;
    service = new ConversationSyncService({ db: fixture.db, runtimes: broker });
  });

  afterEach(async () => {
    service.dispose();
    await recordsHost.dispose();
    await wire.dispose();
    fixture.close();
  });

  function registry() {
    return createConversationRegistry(fixture.db);
  }

  function setHostRecords(...records: ConversationRecord[]): void {
    hostRecords.set(Object.fromEntries(records.map((record) => [record.conversationId, record])));
  }

  it('applies initial host state and then diffs through the same path', async () => {
    setHostRecords(hostRecord({ conversationId: 'conv-1', title: 'Pre-existing' }));

    await service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => {
      expect(registry().getLive('conv-1')).toMatchObject({
        title: 'Pre-existing',
        origin: 'adopted',
        observedStatus: 'present',
        location: 'local',
      });
    });

    // Subsequent host mutations arrive as diffs and route through the same verbs.
    setHostRecords(
      hostRecord({ conversationId: 'conv-1', title: 'Renamed on host' }),
      hostRecord({ conversationId: 'conv-2', title: 'Born after attach' })
    );
    await vi.waitFor(() => {
      expect(registry().getLive('conv-2')).toMatchObject({ title: 'Born after attach' });
      expect(registry().getLive('conv-1')).toMatchObject({ title: 'Renamed on host' });
    });
  });

  it('loses nothing across kill-and-resubscribe: reattach replays full state', async () => {
    setHostRecords(hostRecord({ conversationId: 'conv-1', title: 'First' }));
    await service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => expect(registry().getLive('conv-1')).toBeDefined());

    service.detachHost(LOCAL_HOST_REF);
    // Mutations while detached are invisible to the client...
    setHostRecords(
      hostRecord({ conversationId: 'conv-1', title: 'Renamed while detached' }),
      hostRecord({ conversationId: 'conv-2', title: 'While detached' })
    );
    expect(registry().getLive('conv-2')).toBeUndefined();

    // ...and the reattach's initial state alone recovers everything.
    await service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => {
      expect(registry().getLive('conv-2')).toMatchObject({ title: 'While detached' });
      expect(registry().getLive('conv-1')).toMatchObject({ title: 'Renamed while detached' });
    });
  });

  it('serves cached observations when the host is unreachable; nothing errors, nothing sweeps', async () => {
    setHostRecords(hostRecord({ conversationId: 'conv-1', title: 'Cached' }));
    await service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => expect(registry().getLive('conv-1')).toBeDefined());
    service.detachHost(LOCAL_HOST_REF);

    hostReachable = false;
    await service.attachHost(LOCAL_HOST_REF);

    // No subscription, no sweep: the cached row keeps serving with its last observation.
    const cached = registry().getLive('conv-1');
    expect(cached).toMatchObject({ title: 'Cached', observedStatus: 'present' });
    expect(cached?.lastObservedAt).not.toBeNull();
  });
});
