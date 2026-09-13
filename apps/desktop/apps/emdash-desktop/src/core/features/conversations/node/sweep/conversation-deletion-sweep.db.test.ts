import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { err, ok, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { ManualClock } from '@emdash/shared/testing';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import { ReconcileSweepService } from '@core/services/reconcile-sweep/node/reconcile-sweep-service';
import { applyConversationSnapshot } from '../sync/apply-conversation-snapshot';
import { createConversationDeletionSweepKind } from './conversation-deletion-sweep';

/**
 * The reconcile sweep at the main-db seam (ADR 0006): real tombstone rows on the
 * conversations mirror, the real sweep service with the conversations kind registered,
 * a fake host broker. End-to-end: tombstone offline → host reachable → the removal
 * verb kills any live session and deletes the host index row → the sync delivery
 * confirms the record gone → the tombstone purges, with no user action.
 */
describe('conversation deletion sweep (integration)', () => {
  type SessionKillMock = Mock<(input: { conversationId: string }) => Promise<unknown>>;
  type IndexDeleteMock = Mock<
    (input: { conversationId: string }) => Promise<Result<void, { type: string; message?: string }>>
  >;

  let fixture: Awaited<ReturnType<typeof openFixture>>;
  let scope: Scope;
  let clock: ManualClock;
  let hostVerbs: {
    killAcp: SessionKillMock;
    deleteTui: SessionKillMock;
    deleteRecord: IndexDeleteMock;
    deleteAttachments: SessionKillMock;
  };
  let reachable: boolean;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    scope = createScope({ label: 'conversation-sweep-test' });
    clock = new ManualClock(Date.parse('2026-02-01T00:00:00.000Z'));
    reachable = true;
    hostVerbs = {
      killAcp: vi.fn(async () => ok(undefined)),
      deleteTui: vi.fn(async () => ok(undefined)),
      deleteRecord: vi.fn(async () => ok(undefined)),
      deleteAttachments: vi.fn(async () => ok(undefined)),
    };
  });

  afterEach(async () => {
    await scope.dispose();
    fixture.close();
  });

  function broker() {
    return {
      client: async () =>
        reachable
          ? ok({
              acp: {
                kill: hostVerbs.killAcp,
                deleteAttachments: hostVerbs.deleteAttachments,
              },
              tuiAgents: { delete: hostVerbs.deleteTui },
              conversations: { delete: hostVerbs.deleteRecord },
            })
          : err({ type: 'host-unreachable', message: 'offline' }),
    };
  }

  function createService(): ReconcileSweepService {
    const service = new ReconcileSweepService({
      scope,
      clock,
      onError: (context, error) => {
        throw new Error(`${context}: ${String(error)}`);
      },
    });
    service.registerKind(
      createConversationDeletionSweepKind({ db: fixture.db, runtimes: broker() })
    );
    return service;
  }

  function seedTombstonedConversation(
    id: string,
    options: { workspacePath?: string | null } = {}
  ): void {
    const registry = createConversationRegistry(fixture.db);
    registry.adopt({
      id,
      title: `Conversation ${id}`,
      provider: 'claude',
      type: 'acp',
      location: 'local',
      // Dangling by default: the removal verb must not need a workspace row.
      workspacePath: options.workspacePath ?? `/work/already-gone/${id}`,
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
    registry.tombstone(id, {
      version: '1',
      targetRecordId: id,
      tombstonedAt: clock.now() - 60_000,
    });
  }

  it('converges a tombstone end-to-end: kill sessions + index delete, purge on sync confirmation', async () => {
    seedTombstonedConversation('conv-1');
    const service = createService();

    // The host becomes reachable: the sweep issues the idempotent removal.
    service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(1));
    // Killing the live session is part of the verb, ordered before the index delete.
    expect(hostVerbs.killAcp).toHaveBeenCalledWith({ conversationId: 'conv-1' });
    expect(hostVerbs.deleteTui).toHaveBeenCalledWith({ conversationId: 'conv-1' });
    expect(hostVerbs.deleteRecord).toHaveBeenCalledWith({ conversationId: 'conv-1' });

    // The RPC return asserted nothing: the row is still the visible pending state.
    const registry = createConversationRegistry(fixture.db);
    expect(registry.getLive('conv-1')?.deletionTombstone).toMatchObject({
      targetRecordId: 'conv-1',
    });

    // The sync delivery no longer carries the record: mirror-confirmed gone, purged.
    await applyConversationSnapshot({
      db: fixture.db,
      host: { location: 'local', sshConnectionId: null },
      records: {},
    });
    expect(registry.getLive('conv-1')).toBeUndefined();

    // Converged: later sweeps have nothing to issue.
    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(1);
  });

  it('an already-gone conversation converges silently (idempotent index delete)', async () => {
    seedTombstonedConversation('conv-gone');
    // The host index has no such record; the id-keyed delete no-ops with success.
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).toHaveBeenCalledWith({ conversationId: 'conv-gone' });

    await applyConversationSnapshot({
      db: fixture.db,
      host: { location: 'local', sshConnectionId: null },
      records: {},
    });
    expect(createConversationRegistry(fixture.db).getLive('conv-gone')).toBeUndefined();
  });

  it('rows hard-purged mid-sweep (forget-host) are benign', async () => {
    seedTombstonedConversation('conv-forgotten');
    const registry = createConversationRegistry(fixture.db);
    hostVerbs.deleteRecord.mockImplementation(async () => {
      // Forget-host lands while the removal is in flight: untrack + hard purge.
      registry.untrack(['conv-forgotten'], new Date(clock.now()).toISOString());
      registry.purge(['conv-forgotten']);
      return ok(undefined);
    });
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);
    await service.sweepHost(LOCAL_HOST_REF);

    expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(1);
    expect(registry.getLive('conv-forgotten')).toBeUndefined();
  });

  it('an unreachable broker is not an attempt: the reconnect sweep retries immediately', async () => {
    seedTombstonedConversation('conv-offline');
    reachable = false;
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).not.toHaveBeenCalled();

    reachable = true;
    service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(1));
  });

  it('a failed removal on a reachable host backs off instead of spinning', async () => {
    seedTombstonedConversation('conv-flaky');
    hostVerbs.deleteRecord.mockImplementation(async () =>
      err({ type: 'index-io-error', message: 'disk' })
    );
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(1);

    // Inside the backoff window nothing is re-issued; past it, the backstop retries.
    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(1);
    await clock.advanceBy(10 * 60 * 1000);
    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(2);
  });

  it('a terminal failure records the durable stop on the tombstone and halts auto-retry', async () => {
    seedTombstonedConversation('conv-stuck');
    // Host-decided classification on the RPC error detail (ADR 0006).
    hostVerbs.deleteRecord.mockImplementation(async () =>
      err({ type: 'index-corrupt', class: 'terminal', message: 'index is corrupt' } as never)
    );
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(1);
    expect(
      createConversationRegistry(fixture.db).getLive('conv-stuck')?.deletionTombstone
    ).toMatchObject({ terminalStop: { epoch: 0, message: 'index is corrupt' } });

    // Stopped durably — even a fresh service (app restart) never re-issues.
    await clock.advanceBy(60 * 60 * 1000);
    await service.sweepHost(LOCAL_HOST_REF);
    await createService().sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(1);

    // The durable Retry: the registry epoch bump re-arms exactly this item.
    createConversationRegistry(fixture.db).retryTombstone('conv-stuck');
    await createService().sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteRecord).toHaveBeenCalledTimes(2);
  });

  it('scopes tombstone reads to the swept host', async () => {
    const registry = createConversationRegistry(fixture.db);
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, port, username, auth_type)
         VALUES ('ssh-1', 'box', 'box.example', 22, 'dev', 'agent')`
      )
      .run();
    registry.adopt({
      id: 'conv-remote',
      title: 'Remote conversation',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
    registry.tombstone('conv-remote', {
      version: '1',
      targetRecordId: 'conv-remote',
      tombstonedAt: clock.now() - 60_000,
    });
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);

    expect(hostVerbs.deleteRecord).not.toHaveBeenCalled();
  });
});
