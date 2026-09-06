import { formatHostRef, isLocalHostRef, type HostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import type { ActiveSessionSummary } from '@core/primitives/desktop-host/api/host-contract';
import { log } from '@main/lib/logger';

const SESSION_READ_DEADLINE_MS = 500;

type HostSessionSummary = {
  acpSessions: number;
  tuiSessions: number;
  terminals: number;
  incomplete: boolean;
};

export async function getActiveSessionSummary(
  runtimes: Pick<RuntimeBroker, 'client'>,
  attachedHosts: readonly HostRef[]
): Promise<ActiveSessionSummary> {
  const hostSummaries = await Promise.all(
    attachedHosts.map(async (host) => ({
      host,
      summary: await readHostSessionSummary(runtimes, host),
    }))
  );
  const result: ActiveSessionSummary = {
    acpSessions: 0,
    localTuiSessions: 0,
    remoteSessions: 0,
    terminals: 0,
    incomplete: false,
  };

  for (const { host, summary } of hostSummaries) {
    result.incomplete ||= summary.incomplete;
    if (isLocalHostRef(host)) {
      result.acpSessions += summary.acpSessions;
      result.localTuiSessions += summary.tuiSessions;
      result.terminals += summary.terminals;
    } else {
      result.remoteSessions += summary.acpSessions + summary.tuiSessions;
    }
  }
  return result;
}

async function readHostSessionSummary(
  runtimes: Pick<RuntimeBroker, 'client'>,
  host: HostRef
): Promise<HostSessionSummary> {
  const key = formatHostRef(host);
  const client = runtimes.client(host).then((result) => {
    if (!result.success) throw new Error(result.error.message);
    return result.data;
  });
  const [acpSessions, tuiSessions, terminals] = await Promise.all([
    readWithDeadline(
      `${key} ACP`,
      async () => {
        const snapshot = await (await client).acp.sessions.state(undefined, 'list').snapshot();
        return Object.values(snapshot.data).filter(
          (session) => session.lifecycle === 'working' || session.isGenerating
        ).length;
      },
      0
    ),
    readWithDeadline(
      `${key} TUI`,
      async () => {
        const snapshot = await (
          await client
        ).tuiAgents.sessions
          .state(undefined, 'list')
          .snapshot();
        return Object.values(snapshot.data).filter((session) => session.status === 'running')
          .length;
      },
      0
    ),
    isLocalHostRef(host)
      ? readWithDeadline(
          `${key} terminals`,
          async () => {
            const snapshot = await (
              await client
            ).terminals.sessions
              .state(undefined, 'list')
              .snapshot();
            return Object.values(snapshot.data).filter((session) => session.status === 'running')
              .length;
          },
          0
        )
      : Promise.resolve({ value: 0, incomplete: false }),
  ]);

  return {
    acpSessions: acpSessions.value,
    tuiSessions: tuiSessions.value,
    terminals: terminals.value,
    incomplete: acpSessions.incomplete || tuiSessions.incomplete || terminals.incomplete,
  };
}

interface DeadlineRead<T> {
  value: T;
  incomplete: boolean;
}

async function readWithDeadline<T>(
  name: string,
  read: () => Promise<T>,
  fallback: T
): Promise<DeadlineRead<T>> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const pending = read().then((value) => ({ value, incomplete: false }));
    void pending.catch(() => undefined);
    return await Promise.race([
      pending,
      new Promise<DeadlineRead<T>>((resolve) => {
        timer = setTimeout(
          () => resolve({ value: fallback, incomplete: true }),
          SESSION_READ_DEADLINE_MS
        );
      }),
    ]);
  } catch (error) {
    log.warn(`quit: failed to read ${name} sessions`, { error: String(error) });
    return { value: fallback, incomplete: true };
  } finally {
    if (timer) clearTimeout(timer);
  }
}
