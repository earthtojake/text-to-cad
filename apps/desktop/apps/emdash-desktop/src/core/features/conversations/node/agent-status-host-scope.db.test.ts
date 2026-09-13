import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { loadActiveAgentStatusConversationIds } from './load-active-agent-status-conversation-ids';
import { resetStaleAcpAgentStatuses } from './reset-stale-acp-agent-statuses';
import { resetStaleTuiAgentStatuses } from './reset-stale-tui-agent-statuses';

describe('agent status host scoping', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
    fixture.sqlite
      .prepare(
        `INSERT INTO ssh_connections (id, name, host, port, username, auth_type)
         VALUES ('ssh-1', 'box', 'box.example', 22, 'dev', 'agent')`
      )
      .run();
  });

  afterEach(() => fixture.close());

  it('loads only active, live conversations for the requested host and runtime type', async () => {
    seedConversation('local-acp', 'acp', 'local', null, 'working');
    seedConversation('local-tui', 'pty', 'local', null, 'awaiting-input');
    seedConversation('remote-acp', 'acp', 'remote', 'ssh-1', 'working');
    seedConversation('remote-idle', 'acp', 'remote', 'ssh-1', 'idle');
    seedConversation('remote-untracked', 'acp', 'remote', 'ssh-1', 'working', true);

    await expect(
      loadActiveAgentStatusConversationIds(fixture.db, LOCAL_HOST_REF, 'acp')
    ).resolves.toEqual(['local-acp']);
    await expect(
      loadActiveAgentStatusConversationIds(fixture.db, hostRef('remote', 'ssh-1'), 'acp')
    ).resolves.toEqual(['remote-acp']);
    await expect(
      loadActiveAgentStatusConversationIds(fixture.db, LOCAL_HOST_REF, 'pty')
    ).resolves.toEqual(['local-tui']);
  });

  it('repairs stale local statuses at boot without clearing remote last-known state', async () => {
    seedConversation('local-acp', 'acp', 'local', null, 'working');
    seedConversation('local-tui', 'pty', 'local', null, 'awaiting-input');
    seedConversation('remote-acp', 'acp', 'remote', 'ssh-1', 'working');
    seedConversation('remote-tui', 'pty', 'remote', 'ssh-1', 'awaiting-input');

    await resetStaleAcpAgentStatuses(fixture.db);
    await resetStaleTuiAgentStatuses(fixture.db);

    expect(statusOf('local-acp')).toBe('idle');
    expect(statusOf('local-tui')).toBe('idle');
    expect(statusOf('remote-acp')).toBe('working');
    expect(statusOf('remote-tui')).toBe('awaiting-input');
  });

  function seedConversation(
    id: string,
    type: 'acp' | 'pty',
    location: 'local' | 'remote',
    sshConnectionId: string | null,
    status: string,
    untracked = false
  ): void {
    fixture.sqlite
      .prepare(
        `INSERT INTO conversations
          (id, title, type, location, ssh_connection_id, agent_status, untracked_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      )
      .run(
        id,
        id,
        type,
        location,
        sshConnectionId,
        status,
        untracked ? '2026-01-01T00:00:00.000Z' : null
      );
  }

  function statusOf(id: string): string | null {
    return (
      fixture.sqlite
        .prepare('SELECT agent_status AS status FROM conversations WHERE id = ?')
        .get(id) as { status: string | null }
    ).status;
  }
});
