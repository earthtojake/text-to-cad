import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  createConversationRegistry,
  isAnnotatedConversation,
  type ConversationRegistry,
} from './conversation-registry';

describe('ConversationRegistry', () => {
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

  function registerLinked(registry: ConversationRegistry, id: string): void {
    seedTask(`project-${id}`, `task-${id}`);
    registry.register({
      id,
      projectId: `project-${id}`,
      taskId: `task-${id}`,
      title: 'Linked conversation',
      provider: 'claude',
      type: 'acp',
      location: 'local',
      isInitialConversation: true,
    });
  }

  it('registers linked rows and adopts unlinked mirror rows reusing the host id', () => {
    const registry = createConversationRegistry(fixture.db, {
      now: () => '2026-01-01T00:00:00.000Z',
    });

    registerLinked(registry, 'registered');
    registry.adopt({
      id: 'host-minted-id',
      title: 'Discovered on host',
      provider: 'codex',
      type: 'pty',
      location: 'local',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });

    const registered = registry.getLive('registered');
    expect(registered).toMatchObject({ origin: 'registered', taskId: 'task-registered' });
    expect(registered && isAnnotatedConversation(registered)).toBe(true);

    const adopted = registry.getLive('host-minted-id');
    expect(adopted).toMatchObject({
      origin: 'adopted',
      taskId: null,
      projectId: null,
      observedStatus: 'present',
    });
    expect(adopted && isAnnotatedConversation(adopted)).toBe(false);
  });

  it('claims an adopted row while preserving its sync metadata', () => {
    const registry = createConversationRegistry(fixture.db);
    registry.adopt({
      id: 'conv',
      title: 'Host title',
      provider: 'claude',
      type: 'acp',
      config: { version: '1', type: 'acp' },
      cwd: '/host/repo',
      workspacePath: '/host/repo',
      providerSessionId: null,
      idRegime: 'provider-minted',
      lastSessionActivityAt: '2026-01-02T00:00:00.000Z',
      observedStatus: 'present',
      lastObservedAt: '2026-01-03T00:00:00.000Z',
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-02T00:00:00.000Z',
      location: 'local',
    });
    seedTask('project-conv', 'task-conv');

    const claimed = registry.register({
      id: 'conv',
      projectId: 'project-conv',
      taskId: 'task-conv',
      isInitialConversation: true,
      title: 'Client title',
      provider: 'claude-code',
      type: 'acp',
      config: { version: '1', type: 'acp', model: 'sonnet' },
      cwd: '/client/repo',
      workspacePath: '/client/repo',
      providerSessionId: 'session-1',
      idRegime: 'provider-minted',
      lastSessionActivityAt: '2026-01-04T00:00:00.000Z',
      createdAt: '2026-02-01T00:00:00.000Z',
      updatedAt: '2026-01-04T00:00:00.000Z',
      location: 'local',
    });

    expect(claimed).toMatchObject({
      origin: 'registered',
      projectId: 'project-conv',
      taskId: 'task-conv',
      isInitialConversation: true,
      title: 'Client title',
      provider: 'claude-code',
      config: { version: '1', type: 'acp', model: 'sonnet' },
      cwd: '/client/repo',
      workspacePath: '/client/repo',
      providerSessionId: 'session-1',
      lastSessionActivityAt: '2026-01-04T00:00:00.000Z',
      updatedAt: '2026-01-04T00:00:00.000Z',
      // The sync observation remains valid across the claim.
      observedStatus: 'present',
      lastObservedAt: '2026-01-03T00:00:00.000Z',
      createdAt: '2026-01-01T00:00:00.000Z',
    });
  });

  it('does not let a losing adopt clear registered annotations', () => {
    const registry = createConversationRegistry(fixture.db);
    registerLinked(registry, 'conv');

    const row = registry.adopt({
      id: 'conv',
      title: 'Host delivery',
      provider: 'codex',
      type: 'pty',
      location: 'local',
      lastObservedAt: '2026-01-03T00:00:00.000Z',
      observedStatus: 'present',
    });

    expect(row).toMatchObject({
      origin: 'registered',
      taskId: 'task-conv',
      projectId: 'project-conv',
      isInitialConversation: true,
      title: 'Linked conversation',
      provider: 'claude',
      type: 'acp',
    });
  });

  it('refreshes observation columns wholesale and stamps the observation time', () => {
    const registry = createConversationRegistry(fixture.db);
    registerLinked(registry, 'conv');

    const changed = registry.refresh('conv', {
      title: 'Host title wins',
      providerSessionId: 'session-9',
      idRegime: 'provider-minted',
      lastSessionActivityAt: '2026-01-03T00:00:00.000Z',
      observedStatus: 'present',
      workspacePath: '/hosts/worktree',
      cwd: '/hosts/worktree',
      lastObservedAt: '2026-01-04T00:00:00.000Z',
    });

    expect(changed).toBe(1);
    expect(registry.getLive('conv')).toMatchObject({
      title: 'Host title wins',
      providerSessionId: 'session-9',
      idRegime: 'provider-minted',
      lastSessionActivityAt: '2026-01-03T00:00:00.000Z',
      observedStatus: 'present',
      workspacePath: '/hosts/worktree',
      cwd: '/hosts/worktree',
      lastObservedAt: '2026-01-04T00:00:00.000Z',
      // Annotations untouched by observation writes.
      taskId: 'task-conv',
      isInitialConversation: true,
    });
  });

  it('annotates without touching observation columns', () => {
    const registry = createConversationRegistry(fixture.db);
    registry.adopt({
      id: 'orphan',
      title: 'Orphan',
      provider: 'claude',
      type: 'acp',
      location: 'local',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
      observedStatus: 'present',
    });
    seedTask('project-link', 'task-link');

    const changed = registry.annotate('orphan', {
      taskId: 'task-link',
      projectId: 'project-link',
      agentStatusSeen: 0,
    });

    expect(changed).toBe(1);
    expect(registry.getLive('orphan')).toMatchObject({
      taskId: 'task-link',
      projectId: 'project-link',
      agentStatusSeen: 0,
      // Observations untouched by annotation writes.
      title: 'Orphan',
      lastObservedAt: '2026-01-01T00:00:00.000Z',
    });
  });

  it('untracks and reverts atomically through an optional transaction', () => {
    const registry = createConversationRegistry(fixture.db);
    registerLinked(registry, 'conv');

    const changed = fixture.db.transaction((tx) =>
      registry.untrack(['conv'], '2026-01-05T00:00:00.000Z', tx)
    );
    expect(changed).toBe(1);
    expect(registry.getLive('conv')).toBeUndefined();

    const reverted = registry.revertUntrack(['conv']);
    expect(reverted).toBe(1);
    expect(registry.getLive('conv')).toBeDefined();
  });

  it('refresh skips untracked rows; annotate still reaches them', () => {
    const registry = createConversationRegistry(fixture.db);
    registerLinked(registry, 'conv');
    registry.untrack(['conv'], '2026-01-05T00:00:00.000Z');

    expect(
      registry.refresh('conv', {
        title: 'Should not land',
        lastObservedAt: '2026-01-06T00:00:00.000Z',
      })
    ).toBe(0);
    expect(registry.annotate('conv', { agentStatusSeen: 0 })).toBe(1);
  });

  it('tombstones a live row atomically; the row stays live as the pending state', () => {
    const registry = createConversationRegistry(fixture.db);
    registerLinked(registry, 'conv');

    const changed = registry.tombstone('conv', {
      version: '1',
      targetRecordId: 'conv',
      tombstonedAt: 1_700_000_000_000,
    });

    expect(changed).toBe(1);
    expect(registry.getLive('conv')?.deletionTombstone).toMatchObject({
      targetRecordId: 'conv',
      tombstonedAt: 1_700_000_000_000,
    });
  });

  it('tombstone is first-writer-wins: duplicates and untracked rows write zero rows', () => {
    const registry = createConversationRegistry(fixture.db);
    registerLinked(registry, 'conv');
    registry.tombstone('conv', { version: '1', targetRecordId: 'conv', tombstonedAt: 1 });

    // A double-fire never overwrites the first write's stamp.
    expect(
      registry.tombstone('conv', { version: '1', targetRecordId: 'conv', tombstonedAt: 2 })
    ).toBe(0);
    expect(registry.getLive('conv')?.deletionTombstone).toMatchObject({ tombstonedAt: 1 });

    registerLinked(registry, 'gone');
    registry.untrack(['gone'], '2026-01-05T00:00:00.000Z');
    expect(
      registry.tombstone('gone', { version: '1', targetRecordId: 'gone', tombstonedAt: 1 })
    ).toBe(0);
  });

  it('purges only rows that are already untracked', () => {
    const registry = createConversationRegistry(fixture.db);
    registerLinked(registry, 'tracked');
    registerLinked(registry, 'untracked');
    registry.untrack(['untracked'], '2026-01-05T00:00:00.000Z');

    expect(() => registry.purge(['tracked', 'untracked'])).toThrow(
      /must be untracked before purge/
    );

    expect(registry.purge(['untracked'])).toBe(1);
    expect(registry.revertUntrack(['untracked'])).toBe(0);
    expect(registry.getLive('tracked')).toBeDefined();
  });
});
