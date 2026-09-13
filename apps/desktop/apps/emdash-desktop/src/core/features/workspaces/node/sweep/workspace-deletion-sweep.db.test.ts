import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { ok, type Result } from '@emdash/shared';
import { createScope, type Scope } from '@emdash/shared/concurrency';
import { ManualClock } from '@emdash/shared/testing';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import { createWorkspaceRegistry } from '@core/features/workspaces/api/node/registry';
import { ReconcileSweepService } from '@core/services/reconcile-sweep/node/reconcile-sweep-service';
import { createWorkspaceRegistryWireController } from '../registry-wire-controller';
import { applyWorkspaceRegistrySnapshot } from '../sync/apply-workspace-registry-snapshot';
import { createWorkspaceDeletionSweepKind } from './workspace-deletion-sweep';

/**
 * The reconcile sweep at the main-db seam (ADR 0006): real tombstone rows on the
 * workspaces mirror, the real sweep service with the workspaces kind registered, a
 * fake host broker. End-to-end: tombstone offline → host reachable → the idempotent
 * delete verb runs with the frozen options → the sync delivery confirms the record
 * gone → the tombstone purges, with no user action. Terminal failures stop the loop
 * until the wire affordances (Retry / Untrack-anyway) act.
 */
describe('workspace deletion sweep (integration)', () => {
  type DeleteVerbMock = Mock<
    (input: {
      workspaceId: string;
      deleteBranch?: boolean;
    }) => Promise<Result<void, { type: string; message?: string }>>
  >;

  let fixture: Awaited<ReturnType<typeof openFixture>>;
  let scope: Scope;
  let clock: ManualClock;
  let hostVerbs: {
    deleteWorktree: DeleteVerbMock;
    deleteWorkspace: DeleteVerbMock;
  };
  let reachable: boolean;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    scope = createScope({ label: 'workspace-sweep-test' });
    clock = new ManualClock(Date.parse('2026-02-01T00:00:00.000Z'));
    reachable = true;
    hostVerbs = {
      deleteWorktree: vi.fn(async () => ok(undefined)),
      deleteWorkspace: vi.fn(async () => ok(undefined)),
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
          ? ok({ workspaceRegistry: hostVerbs })
          : { success: false as const, error: { type: 'host-unreachable', message: 'offline' } },
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
      createWorkspaceDeletionSweepKind({
        db: fixture.db,
        runtimes: broker() as never,
      })
    );
    return service;
  }

  function seedTombstonedWorktree(
    id: string,
    options: {
      deleteBranch?: boolean;
      deleteConversations?: boolean;
      kind?: 'worktree' | 'directory';
    } = {}
  ): void {
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordCreationIntent({
      id,
      type: 'local',
      kind: options.kind ?? 'worktree',
      location: 'local',
      sshConnectionId: null,
      path: `/work/${id}`,
    });
    registry.tombstone(id, {
      version: '1',
      targetRecordId: id,
      tombstonedAt: clock.now() - 60_000,
      options: {
        deleteBranch: options.deleteBranch ?? false,
        deleteConversations: options.deleteConversations ?? false,
      },
    });
  }

  it('converges a tombstone end-to-end: verb with frozen options, purge on sync confirmation', async () => {
    seedTombstonedWorktree('wt-1', { deleteBranch: true });
    const service = createService();

    // The host becomes reachable: the sweep issues the idempotent removal.
    service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => expect(hostVerbs.deleteWorktree).toHaveBeenCalledTimes(1));
    expect(hostVerbs.deleteWorktree).toHaveBeenCalledWith({
      workspaceId: 'wt-1',
      deleteBranch: true,
    });

    // The RPC return asserted nothing: the row is still the visible pending state.
    const registry = createWorkspaceRegistry(fixture.db);
    expect(registry.getLive('wt-1')?.deletionTombstone).toMatchObject({ targetRecordId: 'wt-1' });

    // The sync delivery no longer carries the record: mirror-confirmed gone, purged.
    await applyWorkspaceRegistrySnapshot({
      db: fixture.db,
      host: { location: 'local', sshConnectionId: null },
      records: {},
    });
    expect(registry.getLive('wt-1')).toBeUndefined();

    // Converged: later sweeps have nothing to issue.
    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteWorktree).toHaveBeenCalledTimes(1);
  });

  it('routes directory tombstones through deleteWorkspace', async () => {
    seedTombstonedWorktree('dir-1', { kind: 'directory' });
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);

    expect(hostVerbs.deleteWorkspace).toHaveBeenCalledWith({ workspaceId: 'dir-1' });
    expect(hostVerbs.deleteWorktree).not.toHaveBeenCalled();
  });

  it('writes conversation tombstones for the frozen cascade on removal success', async () => {
    seedTombstonedWorktree('wt-conv', { deleteConversations: true });
    const conversations = createConversationRegistry(fixture.db);
    conversations.adopt({
      id: 'conv-here',
      title: 'Conversation',
      provider: 'claude',
      type: 'acp',
      location: 'local',
      workspacePath: '/work/wt-conv',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
    conversations.adopt({
      id: 'conv-elsewhere',
      title: 'Conversation',
      provider: 'claude',
      type: 'acp',
      location: 'local',
      workspacePath: '/work/other',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);

    // Nothing queues anywhere (ADR 0006): the cascade writes durable conversation
    // tombstones and the conversations kind converges them on sweeps of this host.
    expect(conversations.getLive('conv-here')?.deletionTombstone).toMatchObject({
      targetRecordId: 'conv-here',
    });
    expect(conversations.getLive('conv-elsewhere')?.deletionTombstone).toBeNull();
  });

  it('a terminal RPC failure records the durable stop on the tombstone and halts auto-retry', async () => {
    seedTombstonedWorktree('wt-stuck');
    // The host classifies the failure: the delete verb's error detail is terminal.
    hostVerbs.deleteWorktree.mockImplementation(async () => ({
      success: false as const,
      error: {
        type: 'remove-failed',
        stage: 'remove',
        class: 'terminal',
        message: 'worktree is locked',
      },
    }));
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteWorktree).toHaveBeenCalledTimes(1);
    expect(
      createWorkspaceRegistry(fixture.db).getLive('wt-stuck')?.deletionTombstone
    ).toMatchObject({ terminalStop: { epoch: 0, stage: 'remove', message: 'worktree is locked' } });

    // Stopped durably — even a fresh service (app restart) never re-issues.
    await clock.advanceBy(60 * 60_000);
    await service.sweepHost(LOCAL_HOST_REF);
    await createService().sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteWorktree).toHaveBeenCalledTimes(1);
  });

  it('the Retry wire verb durably advances the epoch: sync and restarts never resurrect the stop', async () => {
    seedTombstonedWorktree('wt-stuck');
    const registry = createWorkspaceRegistry(fixture.db);
    registry.recordTombstoneTerminalStop('wt-stuck', {
      epoch: 0,
      stage: 'remove',
      message: 'worktree is locked',
      at: clock.now() - 1_000,
    });
    const service = createService();
    const wire = createWorkspaceRegistryWireController({
      db: fixture.db,
      runtimes: broker() as never,
      sweep: service,
    });

    await wire.call('retryWorkspaceRemoval', { workspaceId: 'wt-stuck' });

    await vi.waitFor(() => expect(hostVerbs.deleteWorktree).toHaveBeenCalledTimes(1));
    // The durable half: the epoch advanced on the row; the stale stop stays but is inert.
    expect(registry.getLive('wt-stuck')?.deletionTombstone).toMatchObject({
      attemptEpoch: 1,
      terminalStop: { epoch: 0 },
    });

    // A registry sync restoring the host-written mark changes nothing, and a fresh
    // service (app restart) still attempts: the stop state is desktop-owned.
    registry.refresh('wt-stuck', {
      lastRemovalAttempt: {
        version: '1',
        stage: 'remove',
        class: 'terminal',
        message: 'worktree is locked',
        at: clock.now(),
      },
    });
    await createService().sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteWorktree).toHaveBeenCalledTimes(2);
  });

  it('the Untrack-anyway wire verb purges the tombstone without touching the host', async () => {
    seedTombstonedWorktree('wt-abandoned');
    const service = createService();
    const wire = createWorkspaceRegistryWireController({
      db: fixture.db,
      runtimes: broker() as never,
      sweep: service,
    });

    await wire.call('abandonWorkspaceRemoval', { workspaceId: 'wt-abandoned' });
    await service.sweepHost(LOCAL_HOST_REF);

    expect(createWorkspaceRegistry(fixture.db).getLive('wt-abandoned')).toBeUndefined();
    expect(hostVerbs.deleteWorktree).not.toHaveBeenCalled();
  });

  it('rows hard-purged mid-sweep (forget-host) are benign', async () => {
    seedTombstonedWorktree('wt-forgotten');
    const registry = createWorkspaceRegistry(fixture.db);
    hostVerbs.deleteWorktree.mockImplementation(async () => {
      // Forget-host lands while the removal is in flight: untrack + hard purge.
      registry.untrack(['wt-forgotten'], new Date(clock.now()).toISOString());
      registry.purge(['wt-forgotten']);
      return ok(undefined);
    });
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);
    await service.sweepHost(LOCAL_HOST_REF);

    expect(hostVerbs.deleteWorktree).toHaveBeenCalledTimes(1);
    expect(registry.getLive('wt-forgotten')).toBeUndefined();
  });

  it('an unreachable broker is not an attempt: the reconnect sweep retries immediately', async () => {
    seedTombstonedWorktree('wt-offline');
    reachable = false;
    const service = createService();

    await service.sweepHost(LOCAL_HOST_REF);
    expect(hostVerbs.deleteWorktree).not.toHaveBeenCalled();

    reachable = true;
    service.attachHost(LOCAL_HOST_REF);
    await vi.waitFor(() => expect(hostVerbs.deleteWorktree).toHaveBeenCalledTimes(1));
  });
});
