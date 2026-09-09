import { formatHostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { observable, runInAction } from 'mobx';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ConversationManagerStore } from '@core/features/conversations/api/browser/conversation-manager';
import type {
  ProjectHostAccess,
  ProjectHostAccessState,
} from '@core/features/projects/api/browser/stores/project-context';

const localSessionHost = () => formatHostRef(LOCAL_HOST_REF);

const hydrateConversation = vi.hoisted(() => vi.fn());
const dehydrateConversation = vi.hoisted(() => vi.fn());
const frontendConnect = vi.hoisted(() => vi.fn());
const frontendDispose = vi.hoisted(() => vi.fn());

vi.mock('@core/features/editor/api/browser/open-file-in-file-editor', () => ({
  makeFileLinkHandlers: () => ({
    onOpenExternal: vi.fn(),
    onOpenFile: vi.fn(),
  }),
}));

vi.mock('@core/features/terminals/api/browser/pty/pty', () => ({
  FrontendPty: class {
    constructor(readonly sessionId: string) {}

    connect = frontendConnect;
    dispose = frontendDispose;
  },
}));

describe('ConversationManagerStore session hydration', () => {
  beforeEach(() => {
    hydrateConversation.mockReset();
    dehydrateConversation.mockReset();
    frontendConnect.mockReset();
    frontendDispose.mockReset();

    hydrateConversation.mockResolvedValue(undefined);
    dehydrateConversation.mockResolvedValue(undefined);
    frontendConnect.mockResolvedValue(undefined);
  });

  it('does not hydrate conversations from the PTY session connect path', async () => {
    const store = new ConversationManagerStore(
      'project-1',
      'task-1',
      [
        {
          id: 'conversation-1',
          projectId: 'project-1',
          taskId: 'task-1',
          providerId: 'codex',
          title: 'Conversation 1',
          lastInteractedAt: null,
          isInitialConversation: false,
        },
      ],
      localSessionHost
    );

    const session = store.sessions.get('conversation-1');
    expect(session).toBeDefined();

    await session?.connect();

    expect(hydrateConversation).not.toHaveBeenCalled();
    expect(frontendConnect).toHaveBeenCalledTimes(1);

    store.dispose();
  });

  it('marks only starting and running TUI sessions active', () => {
    const store = new ConversationManagerStore('project-1', 'task-1', [], localSessionHost);

    (
      store as unknown as {
        handleTuiSessionListChanged(list: Record<string, unknown>): void;
      }
    ).handleTuiSessionListChanged({
      starting: {
        conversationId: 'starting',
        providerId: 'codex',
        sessionId: null,
        status: 'starting',
        cols: 80,
        rows: 24,
        resume: null,
        startedAt: 1,
      },
      running: {
        conversationId: 'running',
        providerId: 'codex',
        sessionId: null,
        status: 'running',
        cols: 80,
        rows: 24,
        resume: null,
        startedAt: 1,
      },
      exited: {
        conversationId: 'exited',
        providerId: 'codex',
        sessionId: null,
        status: 'exited',
        cols: 80,
        rows: 24,
        resume: null,
        startedAt: 1,
      },
    });

    expect(store.activeTuiSessionIds.has('starting')).toBe(true);
    expect(store.activeTuiSessionIds.has('running')).toBe(true);
    expect(store.activeTuiSessionIds.has('exited')).toBe(false);

    store.dispose();
  });

  it('marks closed ACP sessions inactive', () => {
    const store = new ConversationManagerStore('project-1', 'task-1', [], localSessionHost);

    (
      store as unknown as {
        handleAcpSessionListChanged(list: Record<string, unknown>): void;
      }
    ).handleAcpSessionListChanged({
      ready: acpSession('ready', 'ready'),
      closed: acpSession('closed', 'closed'),
    });

    expect(store.activeAcpSessionIds.has('ready')).toBe(true);
    expect(store.activeAcpSessionIds.has('closed')).toBe(false);

    store.dispose();
  });

  it('retains prior runtime observations as stale while offline', () => {
    const host = {
      state: {
        kind: 'degraded',
        situation: 'offline',
        recovery: 'automatic',
      },
      liveAction: {
        kind: 'disabled',
        state: {
          kind: 'degraded',
          situation: 'offline',
          recovery: 'automatic',
        },
      },
    } as ProjectHostAccess;
    const store = new ConversationManagerStore('project-1', 'task-1', [], localSessionHost, host);

    expect(store.runtimeObservation).toEqual({ kind: 'unavailable' });
    (
      store as unknown as {
        handleAcpSessionListChanged(list: Record<string, unknown>): void;
      }
    ).handleAcpSessionListChanged({ ready: acpSession('ready', 'ready') });

    expect(store.runtimeObservation).toEqual({
      kind: 'stale',
      value: {
        activeAcpSessionIds: ['ready'],
        activeTuiSessionIds: [],
      },
    });
    store.dispose();
  });

  it('preserves transcripts and resumes requested sessions after recovery', async () => {
    const state = observable.box<ProjectHostAccessState>({
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    });
    const hostAccess = {
      get state() {
        return state.get();
      },
      get liveAction() {
        const current = state.get();
        return current.kind === 'ready'
          ? ({ kind: 'enabled' } as const)
          : ({ kind: 'disabled', state: current } as const);
      },
    } as ProjectHostAccess;
    const transcript = {
      id: 'conversation-1',
      projectId: 'project-1',
      taskId: 'task-1',
      providerId: 'codex',
      title: 'Preserved transcript',
      lastInteractedAt: null,
      isInitialConversation: false,
    };
    const store = new ConversationManagerStore(
      'project-1',
      'task-1',
      [transcript],
      localSessionHost,
      hostAccess
    );
    const session = store.sessions.get(transcript.id);

    await session?.connect();

    expect(session?.status).toBe('disconnected');
    expect(store.conversations.get(transcript.id)?.data.title).toBe('Preserved transcript');
    expect(frontendConnect).not.toHaveBeenCalled();

    runInAction(() => state.set({ kind: 'ready', hostGeneration: 2 }));
    await vi.waitFor(() => expect(session?.status).toBe('ready'));
    expect(frontendConnect).toHaveBeenCalledTimes(1);
    expect(store.conversations.get(transcript.id)?.data.title).toBe('Preserved transcript');
    store.dispose();
  });
});

function acpSession(conversationId: string, lifecycle: 'ready' | 'closed') {
  return {
    conversationId,
    projectId: 'project-1',
    taskId: 'task-1',
    providerId: 'codex',
    lifecycle,
    isGenerating: false,
    lastStopReason: null,
    lastTurnErrored: false,
    pendingPermissionCount: 0,
    backgroundAgentCount: 0,
    queuedPromptCount: 0,
    title: null,
    updatedAt: 1,
  };
}
