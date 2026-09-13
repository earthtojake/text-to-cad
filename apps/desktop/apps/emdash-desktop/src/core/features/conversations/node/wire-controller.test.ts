import {
  formatHostRef,
  hostRef,
  LOCAL_HOST_REF,
  type HostRef,
} from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import type { LiveSource } from '@emdash/wire/rpc';
import { encodeTopic, isDownloadFileOpenResult, type WireFile } from '@emdash/wire/rpc';
import { describe, expect, it, vi } from 'vitest';
import { conversationsContract } from '../api';
import type { ConversationsRuntimeResolveError as RuntimeResolveError } from '../api/runtime-adapter';
import { createConversationsWireController } from './wire-controller';

vi.mock('@core/features/conversations/node/controller', () => ({
  createConversationOperations: () => ({
    getConversations: vi.fn(),
    createConversation: vi.fn(),
    deleteConversation: vi.fn(),
    hydrateConversation: vi.fn(),
    dehydrateConversation: vi.fn(),
    renameConversation: vi.fn(),
    getConversationsForTask: vi.fn(),
    getConversationsForProject: vi.fn(),
    markConversationSeen: vi.fn(),
  }),
}));
const target = {
  conversationId: 'conversation-1',
  projectId: 'project-1',
  taskId: 'task-1',
  conversationType: 'acp',
  providerId: 'claude',
  sessionId: null,
  modeId: null,
  workspacePath: '/repo',
  host: LOCAL_HOST_REF,
  acpInput: {
    conversationId: 'conversation-1',
    providerId: 'claude',
    cwd: '/repo',
    sessionId: null,
    model: null,
    modeId: null,
  },
} as const;
type TestRuntimeTarget = typeof target;

describe('createConversationsWireController', () => {
  it('passes ACP session start through without a client session id write', async () => {
    const start = vi.fn(async () => ok({ sessionId: 'session-1' }));
    const controller = setupController({
      client: { acp: { start } },
    });

    await expect(
      controller.call('acp.start', { conversationId: target.conversationId })
    ).resolves.toEqual(ok({ sessionId: 'session-1' }));

    // The ACP runtime reports the session id into the conversation index (spec §3.3);
    // the desktop no longer persists it from the response.
    expect(start).toHaveBeenCalledWith(target.acpInput, {});
  });

  it('disables the worker Wire deadline for the turn-long ACP prompt call', async () => {
    const sendPrompt = vi.fn(async () => ok({ queued: false }));
    const controller = setupController({
      client: { acp: { sendPrompt } },
    });
    const input = {
      conversationId: target.conversationId,
      prompt: { text: 'hello' },
    };

    await expect(controller.call('acp.sendPrompt', input)).resolves.toEqual(ok({ queued: false }));

    expect(sendPrompt).toHaveBeenCalledWith(input, { timeoutMs: 0 });
  });

  it('records submitted TUI input only after a successful carriage return', async () => {
    const sendInput = vi.fn(async () => ok(undefined));
    const recordTuiInput = vi.fn(async () => {});
    const controller = setupController({
      client: { tuiAgents: { sendInput } },
      hooks: { recordTuiInput },
    });

    await controller.call('tui.sendInput', {
      conversationId: target.conversationId,
      data: 'hello',
    });
    expect(recordTuiInput).not.toHaveBeenCalled();

    await controller.call('tui.sendInput', {
      conversationId: target.conversationId,
      data: '\r',
    });
    expect(recordTuiInput).toHaveBeenCalledOnce();
    expect(recordTuiInput).toHaveBeenCalledWith(target);
  });

  it('passes uploads and downloads through the resolved client', async () => {
    const uploadAttachment = vi.fn(async () =>
      ok({ id: 'attachment-1', name: 'image.png', mimeType: 'image/png' as const })
    );
    const downloadAttachment = vi.fn(async () =>
      ok({
        meta: { id: 'attachment-1', name: 'image.png', mimeType: 'image/png' as const },
        chunks: async function* () {
          yield new Uint8Array([1, 2, 3]);
        },
      })
    );
    const controller = setupController({
      client: { acp: { uploadAttachment, downloadAttachment } },
    });
    const file = fakeWireFile();

    await controller.call(
      'acp.uploadAttachment',
      { conversationId: target.conversationId, originalPath: '/tmp/image.png' },
      { uploadFile: file }
    );
    expect(uploadAttachment).toHaveBeenCalledWith(
      { conversationId: target.conversationId, originalPath: '/tmp/image.png' },
      file,
      {}
    );

    const result = await controller.call('acp.downloadAttachment', {
      conversationId: target.conversationId,
      attachmentId: 'attachment-1',
    });
    expect(downloadAttachment).toHaveBeenCalledWith(
      { conversationId: target.conversationId, attachmentId: 'attachment-1' },
      {}
    );
    expect(isDownloadFileOpenResult(result)).toBe(true);
    if (!isDownloadFileOpenResult(result)) throw new Error('Expected a download result');
    const chunks: Uint8Array[] = [];
    for await (const chunk of result.data.source as AsyncIterable<Uint8Array>) {
      chunks.push(chunk);
    }
    expect(chunks).toEqual([new Uint8Array([1, 2, 3])]);

    const cancelled = await controller.call('acp.downloadAttachment', {
      conversationId: target.conversationId,
      attachmentId: 'attachment-1',
    });
    if (!isDownloadFileOpenResult(cancelled)) throw new Error('Expected a download result');
    const iterator = (cancelled.data.source as AsyncIterable<Uint8Array>)[Symbol.asyncIterator]();
    await iterator.return?.();
  });

  it('resolves the client for each attached ACP session state', async () => {
    const source: LiveSource = {
      snapshot: async () => ({
        generation: 1,
        sequence: 0,
        timestamp: 0,
        data: { lifecycle: 'active' },
      }),
      subscribe: () => () => {},
    };
    const state = vi.fn(() => ({ asLiveSource: () => source }));
    const controller = setupController({
      client: { acp: { session: { state } } },
    });
    const topic = encodeTopic(conversationsContract.acp.session.states.state.id, {
      conversationId: target.conversationId,
    });

    const lease = controller.acquireLive(topic);
    expect(lease).not.toBeNull();
    await expect(lease?.ready()).resolves.toBe(source);

    await lease?.release();
  });

  it('forwards aggregate ACP sessions through the host encoded in the desktop key', async () => {
    const remoteHost = hostRef('remote', 'ssh-1');
    const resolvedHosts: HostRef[] = [];
    const source: LiveSource = {
      snapshot: async () => ({ generation: 1, sequence: 0, timestamp: 0, data: {} }),
      subscribe: () => () => {},
    };
    const state = vi.fn(() => ({ asLiveSource: () => source }));
    const controller = setupController({
      client: { acp: { sessions: { state } } },
      resolvedHosts,
    });
    const topic = encodeTopic(conversationsContract.acp.sessions.states.list.id, {
      host: formatHostRef(remoteHost),
      projectId: target.projectId,
    });

    const lease = controller.acquireLive(topic);
    await expect(lease?.ready()).resolves.toBe(source);

    expect(resolvedHosts).toEqual([remoteHost]);
    expect(state).toHaveBeenCalledWith(undefined, 'list');
    await lease?.release();
  });

  it('forwards aggregate TUI sessions through the host encoded in the desktop key', async () => {
    const remoteHost = hostRef('remote', 'ssh-2');
    const resolvedHosts: HostRef[] = [];
    const source: LiveSource = {
      snapshot: async () => ({ generation: 1, sequence: 0, timestamp: 0, data: {} }),
      subscribe: () => () => {},
    };
    const state = vi.fn(() => ({ asLiveSource: () => source }));
    const controller = setupController({
      client: { tuiAgents: { sessions: { state } } },
      resolvedHosts,
    });
    const topic = encodeTopic(conversationsContract.tui.sessions.states.list.id, {
      host: formatHostRef(remoteHost),
      projectId: target.projectId,
    });

    const lease = controller.acquireLive(topic);
    await expect(lease?.ready()).resolves.toBe(source);

    expect(resolvedHosts).toEqual([remoteHost]);
    expect(state).toHaveBeenCalledWith(undefined, 'list');
    await lease?.release();
  });

  it('returns RuntimeResolveError from fallible conversation procedures and downloads', async () => {
    const resolveError: RuntimeResolveError = {
      type: 'host-unavailable',
      host: LOCAL_HOST_REF,
      reason: 'runtime-unavailable',
      message: 'Runtime unavailable',
    };
    const controller = setupController({
      client: {},
      runtimeError: resolveError,
    });

    await expect(
      controller.call('acp.start', { conversationId: target.conversationId })
    ).resolves.toEqual(err(resolveError));
    await expect(
      controller.call('acp.downloadAttachment', {
        conversationId: target.conversationId,
        attachmentId: 'attachment-1',
      })
    ).resolves.toEqual(err(resolveError));
  });

  it('requires effective project attachment before live conversation calls', async () => {
    const resolvedHosts: HostRef[] = [];
    const attachmentError = {
      type: 'project-missing' as const,
      projectId: target.projectId,
    };
    const controller = setupController({
      client: {},
      attachmentError,
      resolvedHosts,
    });

    await expect(
      controller.call('acp.sendPrompt', {
        conversationId: target.conversationId,
        prompt: { text: 'hello' },
      })
    ).resolves.toEqual(err(attachmentError));
    await expect(
      controller.call('dehydrateConversation', {
        projectId: target.projectId,
        taskId: target.taskId,
        conversationId: target.conversationId,
      })
    ).resolves.toEqual(err(attachmentError));
    const topic = encodeTopic(conversationsContract.acp.sessions.states.list.id, {
      host: formatHostRef(LOCAL_HOST_REF),
      projectId: target.projectId,
    });
    const lease = controller.acquireLive(topic);
    await expect(lease?.ready()).rejects.toThrow('project-missing');
    await lease?.release();
    expect(resolvedHosts).toEqual([]);
  });
});

function setupController(options: {
  client: object;
  runtimeError?: RuntimeResolveError;
  attachmentError?: { type: 'project-missing'; projectId: string };
  resolvedHosts?: HostRef[];
  hooks?: Partial<{
    persistAcpMode: (target: TestRuntimeTarget, modeId: string) => Promise<void>;
    recordTuiInput: (target: TestRuntimeTarget) => Promise<void>;
  }>;
}) {
  const hooks = {
    persistAcpMode: async () => {},
    recordTuiInput: async () => {},
    ...options.hooks,
  };
  return createConversationsWireController({
    db: {} as never,
    logger: { warn: vi.fn() } as never,
    runtimes: {
      client: async (host: HostRef) => {
        options.resolvedHosts?.push(host);
        return options.runtimeError ? err(options.runtimeError) : ok(options.client);
      },
    } as never,
    workspaceIdentity: {} as never,
    telemetry: { capture: vi.fn() } as never,
    projects: {
      requireAttached: vi.fn(() =>
        options.attachmentError ? err(options.attachmentError) : ok({} as never)
      ),
    },
    taskSessions: { getTask: vi.fn() },
    withCompensation: async ({ action }) => action(),
    hostIsReachable: () => true,
    resolveTarget: async () => target,
    hooks,
  });
}

function fakeWireFile(): WireFile {
  const data = new Uint8Array([1, 2, 3]);
  return {
    name: 'image.png',
    mimeType: 'image/png',
    size: data.byteLength,
    stream: async function* () {
      yield data;
    },
    bytes: async () => data,
    file: async () => ({
      name: 'image.png',
      mimeType: 'image/png',
      size: data.byteLength,
      stream: async function* () {
        yield data;
      },
    }),
    cancel: () => {},
  };
}
