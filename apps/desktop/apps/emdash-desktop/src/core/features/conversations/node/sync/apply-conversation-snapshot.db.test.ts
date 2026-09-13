import type { ConversationRecord } from '@emdash/core/runtimes/conversations/api';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import { applyConversationSnapshot } from './apply-conversation-snapshot';

const LOCAL_HOST = { location: 'local', sshConnectionId: null } as const;

function hostRecord(
  overrides: Partial<ConversationRecord> & { conversationId: string }
): ConversationRecord {
  return {
    provider: 'claude',
    type: 'acp',
    cwd: '/repo/worktree',
    workspacePath: '/repo/worktree',
    idRegime: 'emdash-chosen',
    createdAt: Date.parse('2026-01-01T00:00:00.000Z'),
    title: 'Host truth',
    config: { version: '1', type: 'acp' },
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
 * Convergence from the records live model (spec §5.3-5.4). The cache is never the
 * authority (`conv.cache-not-authority`): a snapshot overwrites cached observation
 * fields unconditionally, and a wiped client fully reconverges by adoption.
 */
describe('applyConversationSnapshot', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  function seedTask(projectId: string, taskId: string): void {
    fixture.sqlite
      .prepare(`INSERT INTO projects (id, name) VALUES (?, ?)`)
      .run(projectId, `project-${projectId}`);
    fixture.sqlite
      .prepare(`INSERT INTO tasks (id, project_id, name, status) VALUES (?, ?, ?, 'running')`)
      .run(taskId, projectId, `task-${taskId}`);
  }

  it('adopts unknown host records unlinked with observations populated (wiped-client reconvergence)', async () => {
    const result = await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {
        'conv-1': hostRecord({ conversationId: 'conv-1', providerSessionId: 'session-1' }),
        'conv-2': hostRecord({ conversationId: 'conv-2', type: 'pty', title: 'Second' }),
      },
      observedAt: '2026-01-03T00:00:00.000Z',
    });

    expect(result).toEqual({
      adopted: 2,
      refreshed: 0,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });

    const registry = createConversationRegistry(fixture.db);
    expect(registry.getLive('conv-1')).toMatchObject({
      origin: 'adopted',
      taskId: null,
      projectId: null,
      title: 'Host truth',
      providerSessionId: 'session-1',
      idRegime: 'emdash-chosen',
      cwd: '/repo/worktree',
      workspacePath: '/repo/worktree',
      observedStatus: 'present',
      lastObservedAt: '2026-01-03T00:00:00.000Z',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-02T00:00:00.000Z',
      location: 'local',
      sshConnectionId: null,
    });
    expect(registry.getLive('conv-2')).toMatchObject({ type: 'pty', title: 'Second' });

    // Reconvergence is idempotent: a replayed snapshot refreshes instead of duplicating.
    const replay = await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {
        'conv-1': hostRecord({ conversationId: 'conv-1', providerSessionId: 'session-1' }),
        'conv-2': hostRecord({ conversationId: 'conv-2', type: 'pty', title: 'Second' }),
      },
    });
    expect(replay).toEqual({
      adopted: 0,
      refreshed: 2,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });
  });

  it('lets host-first creation claim a row already adopted by live sync', async () => {
    seedTask('project-1', 'task-1');
    const registry = createConversationRegistry(fixture.db);
    await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: { 'conv-1': hostRecord({ conversationId: 'conv-1' }) },
      observedAt: '2026-01-03T00:00:00.000Z',
    });

    expect(() =>
      registry.register({
        id: 'conv-1',
        projectId: 'project-1',
        taskId: 'task-1',
        isInitialConversation: true,
        title: 'Client title',
        provider: 'claude',
        type: 'acp',
        config: { version: '1', type: 'acp' },
        cwd: '/repo/worktree',
        workspacePath: '/repo/worktree',
        idRegime: 'provider-minted',
        location: 'local',
      })
    ).not.toThrow();
    expect(registry.getLive('conv-1')).toMatchObject({
      origin: 'registered',
      projectId: 'project-1',
      taskId: 'task-1',
      isInitialConversation: true,
      lastObservedAt: '2026-01-03T00:00:00.000Z',
    });
  });

  it('overwrites cached observations wholesale but never touches annotations', async () => {
    seedTask('project-1', 'task-1');
    const registry = createConversationRegistry(fixture.db);
    registry.register({
      id: 'conv-1',
      projectId: 'project-1',
      taskId: 'task-1',
      isInitialConversation: true,
      title: 'Stale local title',
      provider: 'claude',
      type: 'acp',
      location: 'local',
    });

    const result = await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {
        'conv-1': hostRecord({
          conversationId: 'conv-1',
          title: 'Host renamed this',
          providerSessionId: 'rebound-session',
          lastSessionActivityAt: Date.parse('2026-01-05T00:00:00.000Z'),
        }),
      },
      observedAt: '2026-01-06T00:00:00.000Z',
    });

    expect(result).toEqual({
      adopted: 0,
      refreshed: 1,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });
    expect(registry.getLive('conv-1')).toMatchObject({
      // Host wins wholesale — the cache is not the authority.
      title: 'Host renamed this',
      providerSessionId: 'rebound-session',
      lastSessionActivityAt: '2026-01-05T00:00:00.000Z',
      lastObservedAt: '2026-01-06T00:00:00.000Z',
      // Annotations never appear in host payloads, so the snapshot cannot touch them.
      taskId: 'task-1',
      projectId: 'project-1',
      isInitialConversation: true,
      origin: 'registered',
    });
  });

  it('sweeps unmatched rows: task-linked go visible-missing, unlinked silently untrack', async () => {
    seedTask('project-1', 'task-1');
    const registry = createConversationRegistry(fixture.db);
    registry.register({
      id: 'linked-gone',
      projectId: 'project-1',
      taskId: 'task-1',
      title: 'Linked',
      location: 'local',
    });
    registry.adopt({
      id: 'mirror-gone',
      title: 'Pure mirror',
      location: 'local',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
    });

    const result = await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {},
      observedAt: '2026-01-07T00:00:00.000Z',
    });

    expect(result).toEqual({
      adopted: 0,
      refreshed: 0,
      markedMissing: 1,
      untracked: 1,
      purgedTombstones: 0,
    });
    expect(registry.getLive('linked-gone')).toMatchObject({
      observedStatus: 'missing',
      lastObservedAt: '2026-01-07T00:00:00.000Z',
      taskId: 'task-1',
    });
    expect(registry.getLive('mirror-gone')).toBeUndefined();
  });

  it('purges tombstoned rows once a delivery confirms the record gone — annotation notwithstanding', async () => {
    seedTask('project-1', 'task-1');
    const registry = createConversationRegistry(fixture.db);
    registry.register({
      id: 'tombstoned-linked',
      projectId: 'project-1',
      taskId: 'task-1',
      title: 'Pending deletion',
      location: 'local',
    });
    registry.tombstone('tombstoned-linked', {
      version: '1',
      targetRecordId: 'tombstoned-linked',
      tombstonedAt: Date.parse('2026-01-06T00:00:00.000Z'),
    });

    const result = await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {},
      observedAt: '2026-01-07T00:00:00.000Z',
    });

    // Task-linked would normally go visible-missing; a pending deletion purges instead.
    expect(result).toEqual({
      adopted: 0,
      refreshed: 0,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 1,
    });
    expect(registry.getLive('tombstoned-linked')).toBeUndefined();
  });

  it('keeps a tombstoned row pending while the delivery still carries the record', async () => {
    const registry = createConversationRegistry(fixture.db);
    registry.adopt({
      id: 'tombstoned-alive',
      title: 'Pending deletion',
      location: 'local',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
    registry.tombstone('tombstoned-alive', {
      version: '1',
      targetRecordId: 'tombstoned-alive',
      tombstonedAt: Date.parse('2026-01-06T00:00:00.000Z'),
    });

    const result = await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: { 'tombstoned-alive': hostRecord({ conversationId: 'tombstoned-alive' }) },
    });

    expect(result).toMatchObject({ refreshed: 1, purgedTombstones: 0 });
    expect(registry.getLive('tombstoned-alive')?.deletionTombstone).toMatchObject({
      targetRecordId: 'tombstoned-alive',
    });
  });

  it('scopes the sweep to the snapshot host; other hosts are untouched', async () => {
    const registry = createConversationRegistry(fixture.db);
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, port, username, auth_type)
         VALUES ('ssh-1', 'box', 'box.example', 22, 'dev', 'agent')`
      )
      .run();
    registry.adopt({
      id: 'remote-conv',
      title: 'Lives on the SSH host',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });

    const result = await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: {},
    });

    expect(result).toEqual({
      adopted: 0,
      refreshed: 0,
      markedMissing: 0,
      untracked: 0,
      purgedTombstones: 0,
    });
    expect(registry.getLive('remote-conv')).toMatchObject({ observedStatus: 'present' });
  });

  it('re-homes a duplicated id to the last-observed host', async () => {
    const registry = createConversationRegistry(fixture.db);
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, port, username, auth_type)
         VALUES ('ssh-1', 'box', 'box.example', 22, 'dev', 'agent')`
      )
      .run();
    registry.adopt({
      id: 'cloned-conv',
      title: 'Cloned state dir',
      location: 'remote',
      sshConnectionId: 'ssh-1',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
    });

    await applyConversationSnapshot({
      db: fixture.db,
      host: LOCAL_HOST,
      records: { 'cloned-conv': hostRecord({ conversationId: 'cloned-conv' }) },
    });

    expect(registry.getLive('cloned-conv')).toMatchObject({
      location: 'local',
      sshConnectionId: null,
    });
  });
});
