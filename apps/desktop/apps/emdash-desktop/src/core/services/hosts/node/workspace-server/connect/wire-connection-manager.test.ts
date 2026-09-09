import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { PROTOCOL_VERSION, workspaceWireContract } from '@emdash/core/workspace-server';
import { retrySchedules } from '@emdash/shared/scheduling';
import { createManualClock, deferred, waitFor } from '@emdash/shared/testing';
import { defineContract, type WireTransport } from '@emdash/wire/rpc';
import { cell, expose, remote, snapshot } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { describe, expect, it, vi } from 'vitest';
import type { z } from 'zod';
import {
  createTestRuntimeClients,
  createTestWorkspaceWireController,
} from '../../../../../../../../workspace-server/src/testing/controller';
import { serveSocket } from '../../../../../../../../workspace-server/src/wire/serve-socket';
import type { LocalWorkspaceServerTarget } from '../../../api/targets';
import { workspaceServerTargetKey } from '../targets';
import { openLocalWorkspaceServerTransport } from './local-socket-transport';
import {
  createWireConnectionManager,
  workspaceServerReconnectSchedule,
} from './wire-connection-manager';

type AcpSessionList = z.infer<typeof workspaceWireContract.acp.sessions.states.list.dataSchema>;
type AcpSessionSummary = AcpSessionList[string];

describe('WireConnectionManager', () => {
  it('keys SSH targets by connection id and socket path', () => {
    expect(
      workspaceServerTargetKey({
        kind: 'ssh',
        sshConnectionId: 'ssh-one',
        socketPath: '/run/workspace.sock',
      })
    ).not.toBe(
      workspaceServerTargetKey({
        kind: 'ssh',
        sshConnectionId: 'ssh-two',
        socketPath: '/run/workspace.sock',
      })
    );
  });

  it('pins one initialized client and reinitializes it after a daemon restart', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-workspace-client-'));
    const target = localTarget(join(directory, 'workspace.sock'));
    let server = await serveSocket(
      createTestWorkspaceWireController({}, { daemonId: 'daemon-one', appVersion: '1.2.3' }),
      { socketPath: target.socketPath }
    );
    const manager = createWireConnectionManager({
      idleTtlMs: 0,
      retrySchedule: retrySchedules.sequence([5], { repeatLast: true }),
    });

    try {
      const [first, second] = await Promise.all([manager.client(target), manager.client(target)]);
      expect(first).toBe(second);
      expect(first.currentHandshake()).toMatchObject({
        protocolVersion: PROTOCOL_VERSION,
        server: { daemonId: 'daemon-one', appVersion: '1.2.3' },
      });

      await server.dispose();
      const replacement = first.ready();
      server = await serveSocket(
        createTestWorkspaceWireController({}, { daemonId: 'daemon-two' }),
        { socketPath: target.socketPath }
      );

      await expect(replacement).resolves.toMatchObject({ server: { daemonId: 'daemon-two' } });
    } finally {
      await manager.dispose();
      await server.dispose();
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('re-delivers a full live-model snapshot to a converger held across reconnect', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-workspace-client-'));
    const target = localTarget(join(directory, 'workspace.sock'));
    const sessionsList = cell<AcpSessionList>({
      first: acpSummary('first'),
    });
    const sessionsHost = expose(
      workspaceWireContract.acp.sessions,
      { list: sessionsList },
      { publish: { list: 'diff' } }
    );
    const sessionsContract = defineContract({
      acp: defineContract({ sessions: workspaceWireContract.acp.sessions }),
    });
    const sessionsWire = createTestWire(sessionsContract, {
      acp: { sessions: sessionsHost },
    });
    const baseClients = createTestRuntimeClients();
    const acp = { ...baseClients.acp, sessions: sessionsWire.client.acp.sessions };
    let server = await serveSocket(createTestWorkspaceWireController({ acp }), {
      socketPath: target.socketPath,
    });
    const manager = createWireConnectionManager({
      retrySchedule: retrySchedules.sequence([5], { repeatLast: true }),
    });
    const connection = await manager.client(target);
    const sessions = remote(workspaceWireContract.acp.sessions, connection.client.acp.sessions);
    const list = sessions(undefined).states.list;

    try {
      await list.refresh();
      expect(snapshot(list).value).toEqual({ first: acpSummary('first') });

      await server.dispose();
      sessionsList.set({ second: acpSummary('second') });
      server = await serveSocket(createTestWorkspaceWireController({ acp }), {
        socketPath: target.socketPath,
      });

      await waitFor(() => snapshot(list).value?.['second']?.conversationId === 'second');
      expect(snapshot(list).value).toEqual({ second: acpSummary('second') });
    } finally {
      await sessions.dispose();
      await manager.dispose();
      await server.dispose();
      await sessionsWire.dispose();
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('releases the affected pin and cache entry before reporting connection loss', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-workspace-client-'));
    const socketTarget = localTarget(join(directory, 'workspace.sock'));
    const target = {
      kind: 'ssh' as const,
      sshConnectionId: 'ssh-one',
      socketPath: socketTarget.socketPath,
    };
    const server = await serveSocket(createTestWorkspaceWireController(), {
      socketPath: socketTarget.socketPath,
    });
    let openCount = 0;
    const manager = createWireConnectionManager({
      protocolVersion: '999.0.0',
      retrySchedule: retrySchedules.sequence([1], { repeatLast: true }),
      openTransport: async () => {
        openCount += 1;
        return openLocalWorkspaceServerTransport(socketTarget);
      },
    });
    const lost = deferred<void>();
    const onConnectionLost = vi.fn(() => lost.resolve());
    manager.onConnectionLost(onConnectionLost);

    try {
      await expect(manager.client(target)).rejects.toMatchObject({
        name: 'WorkspaceServerProtocolError',
        details: { action: 'upgrade-server' },
      });
      await lost.promise;
      expect(onConnectionLost).toHaveBeenCalledWith(
        target,
        expect.objectContaining({ name: 'WorkspaceServerProtocolError' })
      );

      await expect(manager.client(target)).rejects.toMatchObject({
        name: 'WorkspaceServerProtocolError',
      });
      expect(openCount).toBe(2);
    } finally {
      await manager.dispose();
      await server.dispose();
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('invalidates only pins belonging to the requested SSH connection', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-workspace-client-'));
    const socketTarget = localTarget(join(directory, 'workspace.sock'));
    const server = await serveSocket(createTestWorkspaceWireController(), {
      socketPath: socketTarget.socketPath,
    });
    const manager = createWireConnectionManager({
      openTransport: () => openLocalWorkspaceServerTransport(socketTarget),
    });
    const firstTarget = {
      kind: 'ssh' as const,
      sshConnectionId: 'ssh-one',
      socketPath: socketTarget.socketPath,
    };
    const secondTarget = {
      kind: 'ssh' as const,
      sshConnectionId: 'ssh-two',
      socketPath: socketTarget.socketPath,
    };

    try {
      const first = await manager.client(firstTarget);
      const second = await manager.client(secondTarget);
      await manager.invalidateConnection('ssh-one');

      await expect(manager.client(firstTarget)).resolves.not.toBe(first);
      await expect(manager.client(secondTarget)).resolves.toBe(second);
    } finally {
      await manager.dispose();
      await server.dispose();
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('survives several delayed reconnect attempts without reporting connection loss', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-workspace-client-'));
    const target = localTarget(join(directory, 'workspace.sock'));
    let server = await serveSocket(
      createTestWorkspaceWireController({}, { daemonId: 'delayed-one' }),
      { socketPath: target.socketPath }
    );
    let openCount = 0;
    const onConnectionLost = vi.fn();
    const manager = createWireConnectionManager({
      retrySchedule: retrySchedules.sequence([5, 5, 5, 5, 50]),
      openTransport: async (nextTarget) => {
        openCount += 1;
        if (nextTarget.kind !== 'local-socket') throw new Error('Expected local target');
        return await openLocalWorkspaceServerTransport(nextTarget);
      },
    });
    manager.onConnectionLost(onConnectionLost);

    try {
      const connection = await manager.client(target);
      await server.dispose();
      const replacement = connection.ready();
      await waitFor(() => openCount >= 5);
      server = await serveSocket(
        createTestWorkspaceWireController({}, { daemonId: 'delayed-two' }),
        { socketPath: target.socketPath }
      );

      await expect(replacement).resolves.toMatchObject({ server: { daemonId: 'delayed-two' } });
      expect(onConnectionLost).not.toHaveBeenCalled();
      await expect(manager.client(target)).resolves.toBe(connection);
    } finally {
      await manager.dispose();
      await server.dispose();
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('keeps retrying beyond the SSH manager backoff window before becoming terminal', () => {
    const delays = Array.from({ length: 9 }, (_, index) =>
      workspaceServerReconnectSchedule.delayFor(index)
    );
    const total = delays.reduce<number>((sum, delay) => sum + (delay ?? 0), 0);

    expect(total).toBeGreaterThanOrEqual(90_000);
    expect(workspaceServerReconnectSchedule.delayFor(9)).toBeUndefined();
  });

  it('dials once, handshakes, and closes the probe transport', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'emdash-workspace-dial-'));
    const target = localTarget(join(directory, 'workspace.sock'));
    const server = await serveSocket(
      createTestWorkspaceWireController({}, { daemonId: 'dial-daemon' }),
      { socketPath: target.socketPath }
    );
    let closeCount = 0;
    const manager = createWireConnectionManager({
      openTransport: async (next) => {
        if (next.kind !== 'local-socket') throw new Error('Expected local target');
        const inner = await openLocalWorkspaceServerTransport(next);
        return {
          ...inner,
          close() {
            closeCount += 1;
            inner.close?.();
          },
        };
      },
    });

    try {
      const handshake = await manager.dialOnce(target);
      expect(handshake.server.daemonId).toBe('dial-daemon');
      expect(closeCount).toBe(1);
    } finally {
      await manager.dispose();
      await server.dispose();
      await rm(directory, { recursive: true, force: true });
    }
  });

  it('closes a transport that opens after the dial timeout', async () => {
    const clock = createManualClock();
    const opened = deferred<WireTransport>();
    const close = vi.fn();
    const manager = createWireConnectionManager({
      clock,
      openTransport: () => opened.promise,
    });
    const pending = manager.dialOnce(
      { kind: 'local-socket', socketPath: '/tmp/late-workspace.sock' },
      { timeoutMs: 1 }
    );

    try {
      const rejected = expect(pending).rejects.toMatchObject({ name: 'TimeoutError' });
      await clock.advanceBy(1);
      await rejected;
      opened.resolve({
        post: vi.fn(),
        onMessage: () => () => {},
        onDisconnect: () => () => {},
        close,
      });
      await Promise.resolve();
      await Promise.resolve();

      expect(close).toHaveBeenCalledOnce();
    } finally {
      await manager.dispose();
    }
  });
});

function localTarget(socketPath: string): LocalWorkspaceServerTarget {
  return { kind: 'local-socket', socketPath };
}

function acpSummary(conversationId: string): AcpSessionSummary {
  return {
    conversationId,
    providerId: 'codex',
    lifecycle: 'working',
    isGenerating: true,
    lastStopReason: null,
    lastTurnErrored: false,
    pendingPermissionCount: 0,
    backgroundAgentCount: 0,
    queuedPromptCount: 0,
    title: null,
    updatedAt: 1,
  };
}
