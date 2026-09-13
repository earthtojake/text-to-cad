import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import type { ConversationsRuntimeBroker } from '@core/features/conversations/api/runtime-adapter';
import type { ConversationInsert } from '@core/services/app-db/node/schema';
import { ConversationBackfillService } from './conversation-backfill';

/**
 * Upgrade backfill (spec §8): pre-existing client rows flow upward as idempotent host
 * `create` requests, once per host, tracked by a per-host completed flag. Interruption
 * resumes on the next attempt; a never-reachable host leaves its rows untouched.
 */
describe('ConversationBackfillService', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;
  let create: Mock<(input: unknown) => Promise<unknown>>;
  let reportProviderSessionId: Mock<(input: unknown) => Promise<unknown>>;
  let reachable: boolean;
  let service: ConversationBackfillService;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    create = vi.fn(async () => ({ success: true as const, data: {} }));
    reportProviderSessionId = vi.fn(async () => ({ success: true as const, data: undefined }));
    reachable = true;
    const broker = {
      client: async () =>
        reachable
          ? {
              success: true,
              data: {
                conversations: { create, reports: { providerSessionId: reportProviderSessionId } },
              },
            }
          : { success: false, error: { type: 'host-unavailable', message: 'offline' } },
    } as unknown as ConversationsRuntimeBroker;
    service = new ConversationBackfillService({ db: fixture.db, runtimes: broker });
  });

  afterEach(() => {
    fixture.close();
  });

  function seedRow(id: string, overrides: Partial<ConversationInsert> = {}): void {
    createConversationRegistry(fixture.db).register({
      id,
      projectId: null,
      taskId: null,
      title: `Conversation ${id}`,
      provider: 'claude',
      type: 'acp',
      cwd: '/work/repo',
      workspacePath: '/work/repo',
      idRegime: 'provider-minted',
      createdAt: '2026-01-01T00:00:00.000Z',
      location: 'local',
      sshConnectionId: null,
      ...overrides,
    });
  }

  function seedRemoteConnection(connectionId: string): void {
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, username) VALUES (?, ?, 'example.test', 'user')`
      )
      .run(connectionId, connectionId);
  }

  async function run(host: HostRef = LOCAL_HOST_REF): Promise<void> {
    await service.backfillHost(host);
  }

  it('replays each live row of the host as a create seed and runs exactly once', async () => {
    seedRow('conv-1');
    seedRow('conv-2', { title: 'Second', type: 'pty', idRegime: 'emdash-chosen' });
    seedRemoteConnection('conn-1');
    seedRow('conv-remote', { location: 'remote', sshConnectionId: 'conn-1' });
    createConversationRegistry(fixture.db).untrack(['conv-2'], '2026-01-02T00:00:00.000Z');
    seedRow('conv-3', { title: 'Third', providerSessionId: 'sess-3' });

    await run();

    // Host-scoped and live-only: the remote row and the untracked row are not replayed.
    const createdIds = create.mock.calls
      .map(([input]) => (input as { conversationId: string }).conversationId)
      .sort();
    expect(createdIds).toEqual(['conv-1', 'conv-3']);
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        conversationId: 'conv-1',
        provider: 'claude',
        type: 'acp',
        cwd: '/work/repo',
        workspacePath: '/work/repo',
        idRegime: 'provider-minted',
        createdAt: Date.parse('2026-01-01T00:00:00.000Z'),
        title: 'Conversation conv-1',
      })
    );
    // The cached resume handle is seeded so convergence does not null it out.
    expect(reportProviderSessionId).toHaveBeenCalledTimes(1);
    expect(reportProviderSessionId).toHaveBeenCalledWith({
      conversationId: 'conv-3',
      providerSessionId: 'sess-3',
    });

    // The per-host flag prevents re-runs.
    create.mockClear();
    await run();
    expect(create).not.toHaveBeenCalled();
  });

  it('tracks the flag per host: the remote sweep runs independently of the local one', async () => {
    seedRemoteConnection('conn-1');
    seedRow('conv-remote', { location: 'remote', sshConnectionId: 'conn-1' });

    await run();
    expect(create).not.toHaveBeenCalled();

    await run(hostRef('remote', 'conn-1'));
    expect(create).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ conversationId: 'conv-remote' }));
  });

  it('resumes after an interrupted sweep; idempotent creates make the replay safe', async () => {
    seedRow('conv-1');
    seedRow('conv-2', { title: 'Second' });
    create.mockImplementationOnce(async () => ({ success: true as const, data: {} }));
    create.mockImplementationOnce(async () => {
      throw new Error('transport dropped');
    });

    await run();
    expect(create).toHaveBeenCalledTimes(2);

    // The flag stayed unset, so the next attempt walks every row again from the top.
    create.mockClear();
    await run();
    expect(create).toHaveBeenCalledTimes(2);

    create.mockClear();
    await run();
    expect(create).not.toHaveBeenCalled();
  });

  it('leaves rows of an unreachable host as stale observations; no flag, no calls', async () => {
    seedRow('conv-1');
    reachable = false;

    await run();
    expect(create).not.toHaveBeenCalled();
    expect(createConversationRegistry(fixture.db).getLive('conv-1')).toBeDefined();

    // The obligation never expires: the first reachable attempt completes it.
    reachable = true;
    await run();
    expect(create).toHaveBeenCalledTimes(1);
  });

  it('skips rows with incomplete seeds without blocking the sweep', async () => {
    seedRow('conv-partial', { provider: null, type: null });
    seedRow('conv-full');

    await run();
    expect(create).toHaveBeenCalledTimes(1);
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ conversationId: 'conv-full' }));

    // The unfillable row stays a live cached observation, and the sweep still completed.
    expect(createConversationRegistry(fixture.db).getLive('conv-partial')).toBeDefined();
    create.mockClear();
    await run();
    expect(create).not.toHaveBeenCalled();
  });

  it('continues past a host-rejected create (divergent immutable identity)', async () => {
    seedRow('conv-1');
    seedRow('conv-2', { title: 'Second' });
    const errors: string[] = [];
    const broker = {
      client: async () => ({
        success: true,
        data: {
          conversations: { create, reports: { providerSessionId: reportProviderSessionId } },
        },
      }),
    } as unknown as ConversationsRuntimeBroker;
    service = new ConversationBackfillService({
      db: fixture.db,
      runtimes: broker,
      onError: (context) => errors.push(context),
    });
    create.mockImplementationOnce(async () => ({
      success: false as const,
      error: { type: 'immutable-field-mismatch', message: 'id reuse' },
    }));

    await run();
    expect(create).toHaveBeenCalledTimes(2);
    expect(errors).toHaveLength(1);

    create.mockClear();
    await run();
    expect(create).not.toHaveBeenCalled();
  });
});
