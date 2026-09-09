import { formatHostRef, hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { getActiveSessionSummary } from './active-session-summary';

vi.mock('@main/lib/logger', () => ({
  log: { warn: vi.fn() },
}));

describe('getActiveSessionSummary', () => {
  it('counts local stop candidates and remote ACP/TUI sessions across attached hosts', async () => {
    const remote = hostRef('remote', 'ssh-1');
    const runtimes = broker({
      [formatHostRef(LOCAL_HOST_REF)]: runtimeClient({
        acp: {
          working: { lifecycle: 'working', isGenerating: false },
          generating: { lifecycle: 'ready', isGenerating: true },
          idle: { lifecycle: 'ready', isGenerating: false },
        },
        tui: {
          running: { status: 'running' },
          starting: { status: 'starting' },
          exited: { status: 'exited' },
        },
        terminals: {
          terminal: { status: 'running' },
          exited: { status: 'exited' },
        },
      }),
      [formatHostRef(remote)]: runtimeClient({
        acp: { working: { lifecycle: 'working', isGenerating: false } },
        tui: { running: { status: 'running' } },
      }),
    });

    await expect(
      getActiveSessionSummary(runtimes as never, [LOCAL_HOST_REF, remote])
    ).resolves.toEqual({
      acpSessions: 2,
      localTuiSessions: 1,
      remoteSessions: 2,
      terminals: 1,
      incomplete: false,
    });
  });

  it('marks the summary incomplete when an attempted host read misses the deadline', async () => {
    vi.useFakeTimers();
    let rejectLateRead!: (error: Error) => void;
    const local = runtimeClient({});
    local.acp = clientWithSnapshot(
      () =>
        new Promise((_, reject) => {
          rejectLateRead = reject;
        })
    );
    const pending = getActiveSessionSummary(
      broker({ [formatHostRef(LOCAL_HOST_REF)]: local }) as never,
      [LOCAL_HOST_REF]
    );
    await vi.advanceTimersByTimeAsync(500);

    await expect(pending).resolves.toEqual({
      acpSessions: 0,
      localTuiSessions: 0,
      remoteSessions: 0,
      terminals: 0,
      incomplete: true,
    });
    rejectLateRead(new Error('late worker failure'));
    await Promise.resolve();
    vi.useRealTimers();
  });

  it('marks the summary incomplete when an attempted host read fails', async () => {
    const local = runtimeClient({});
    local.acp = clientWithSnapshot(async () => {
      throw new Error('worker unavailable');
    });

    await expect(
      getActiveSessionSummary(broker({ [formatHostRef(LOCAL_HOST_REF)]: local }) as never, [
        LOCAL_HOST_REF,
      ])
    ).resolves.toEqual({
      acpSessions: 0,
      localTuiSessions: 0,
      remoteSessions: 0,
      terminals: 0,
      incomplete: true,
    });
  });

  it('does not attempt detached remote hosts', async () => {
    const client = vi.fn(async () => ok(runtimeClient({})));

    await expect(
      getActiveSessionSummary({ client } as never, [LOCAL_HOST_REF])
    ).resolves.toMatchObject({ incomplete: false, remoteSessions: 0 });
    expect(client).toHaveBeenCalledTimes(1);
    expect(client).toHaveBeenCalledWith(LOCAL_HOST_REF);
  });
});

function broker(clients: Record<string, ReturnType<typeof runtimeClient>>) {
  return {
    client: vi.fn(async (host) => {
      const client = clients[formatHostRef(host)];
      if (!client) throw new Error(`Missing client for ${formatHostRef(host)}`);
      return ok(client);
    }),
  };
}

function runtimeClient(data: {
  acp?: Record<string, unknown>;
  tui?: Record<string, unknown>;
  terminals?: Record<string, unknown>;
}) {
  return {
    acp: clientWithSessions(data.acp ?? {}),
    tuiAgents: clientWithSessions(data.tui ?? {}),
    terminals: clientWithSessions(data.terminals ?? {}),
  };
}

function clientWithSessions(data: Record<string, unknown>) {
  return clientWithSnapshot(async () => ({ data }));
}

function clientWithSnapshot(snapshot: () => Promise<unknown>) {
  return {
    sessions: {
      state: () => ({ snapshot }),
    },
  };
}
