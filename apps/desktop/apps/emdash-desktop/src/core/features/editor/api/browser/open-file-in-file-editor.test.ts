import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import {
  makeFileLinkHandlers,
  openFileInAdjacentPane,
  openFileInTaskEditor,
} from './open-file-in-file-editor';

const mocks = vi.hoisted(() => ({
  getTaskStore: vi.fn(),
  getWorkspace: vi.fn(),
  openFile: vi.fn(),
  openPath: vi.fn(),
}));

vi.mock('@core/features/tasks/api/browser/task-state/task-selectors', () => ({
  asProvisioned: (task: unknown) => task,
  getTaskStore: mocks.getTaskStore,
}));

vi.mock('@core/features/workbench/api/browser/open-file', () => ({
  openFile: mocks.openFile,
}));

vi.mock('@core/features/workspaces/api/browser/stores/workspace-registry', () => ({
  workspaceRegistry: { get: mocks.getWorkspace },
}));

vi.mock('@core/primitives/desktop-host/browser/host-client', () => ({
  getHostClient: async () => ({ openPath: mocks.openPath }),
}));

async function flushMicrotasks() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('task file opening', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getTaskStore.mockReturnValue({ workspaceId: 'workspace-1' });
    mocks.getWorkspace.mockReturnValue({
      workspaceId: 'workspace-1',
      path: '/repo',
    });
    mocks.openPath.mockResolvedValue({ success: true, data: undefined });
  });

  it('resolves a task-relative path and opens it through the openFile seam with reveal', async () => {
    await openFileInTaskEditor('project-1', 'task-1', 'src/chat-link.ts');

    expect(mocks.openFile).toHaveBeenCalledWith(
      hostFileRefFromNativePath('/repo/src/chat-link.ts'),
      { context: { projectId: 'project-1', taskId: 'task-1' }, target: 'active', reveal: true }
    );
  });

  it('carries the workspace SSH connection into the file identity', async () => {
    mocks.getWorkspace.mockReturnValue({
      workspaceId: 'workspace-1',
      path: '/repo',
      sshConnectionId: 'ssh-1',
    });

    await openFileInTaskEditor('project-1', 'task-1', 'src/chat-link.ts');

    expect(mocks.openFile).toHaveBeenCalledWith(
      hostFileRefFromNativePath('/repo/src/chat-link.ts', 'ssh-1'),
      expect.anything()
    );
  });

  it('targets the adjacent pane for diff-header opens', async () => {
    await openFileInAdjacentPane('project-1', 'task-1', 'src/diff-link.ts');

    expect(mocks.openFile).toHaveBeenCalledWith(
      hostFileRefFromNativePath('/repo/src/diff-link.ts'),
      {
        context: { projectId: 'project-1', taskId: 'task-1' },
        target: 'right',
        reveal: true,
      }
    );
  });

  it('opens absolute paths outside the workspace through the same seam, never the OS', async () => {
    await openFileInTaskEditor('project-1', 'task-1', '/outside/notes.txt');

    expect(mocks.openFile).toHaveBeenCalledWith(
      hostFileRefFromNativePath('/outside/notes.txt'),
      expect.anything()
    );
    expect(mocks.openPath).not.toHaveBeenCalled();
  });

  it('resolves parent-relative paths outside the workspace through the same seam', async () => {
    mocks.getWorkspace.mockReturnValue({
      workspaceId: 'workspace-1',
      path: '/repo/worktree',
    });

    await openFileInTaskEditor('project-1', 'task-1', '../shared/types.ts');

    expect(mocks.openFile).toHaveBeenCalledWith(
      hostFileRefFromNativePath('/repo/shared/types.ts'),
      expect.anything()
    );
    expect(mocks.openPath).not.toHaveBeenCalled();
  });

  it('resolves absolute paths outside a remote workspace onto the remote host', async () => {
    mocks.getWorkspace.mockReturnValue({
      workspaceId: 'workspace-1',
      path: '/home/dev/repo',
      sshConnectionId: 'ssh-1',
    });

    await openFileInTaskEditor('project-1', 'task-1', '/tmp/agent-notes.md');

    expect(mocks.openFile).toHaveBeenCalledWith(
      hostFileRefFromNativePath('/tmp/agent-notes.md', 'ssh-1'),
      expect.anything()
    );
    expect(mocks.openPath).not.toHaveBeenCalled();
  });

  it('does nothing for spellings that cannot form a path', async () => {
    await openFileInTaskEditor('project-1', 'task-1', 'src/\u0000bad.ts');

    expect(mocks.openFile).not.toHaveBeenCalled();
    expect(mocks.openPath).not.toHaveBeenCalled();
  });
});

describe('makeFileLinkHandlers', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getTaskStore.mockReturnValue({ workspaceId: 'workspace-1' });
    mocks.getWorkspace.mockReturnValue({ workspaceId: 'workspace-1', path: '/repo' });
    mocks.openPath.mockResolvedValue({ success: true, data: undefined });
  });

  it('routes conversation file links to the adjacent pane with no existence precheck', async () => {
    const handlers = makeFileLinkHandlers('project-1', 'task-1', { target: 'right' });
    handlers.onOpenFile('docs/spec-the-agent-mentioned.md');
    await flushMicrotasks();

    expect(mocks.openFile).toHaveBeenCalledWith(
      hostFileRefFromNativePath('/repo/docs/spec-the-agent-mentioned.md'),
      {
        context: { projectId: 'project-1', taskId: 'task-1' },
        target: 'right',
        reveal: true,
      }
    );
    expect(mocks.openPath).not.toHaveBeenCalled();
  });

  it('keeps the active-pane default for non-conversation terminal links', async () => {
    const handlers = makeFileLinkHandlers('project-1', 'task-1');
    handlers.onOpenFile('src/terminal-link.ts');
    await flushMicrotasks();

    expect(mocks.openFile).toHaveBeenCalledWith(
      hostFileRefFromNativePath('/repo/src/terminal-link.ts'),
      {
        context: { projectId: 'project-1', taskId: 'task-1' },
        target: 'active',
        reveal: true,
      }
    );
  });

  it('routes onOpenExternal to the explicit openWithOS verb', async () => {
    const handlers = makeFileLinkHandlers('project-1', 'task-1');
    handlers.onOpenExternal('/outside/report.pdf');
    await flushMicrotasks();

    expect(mocks.openPath).toHaveBeenCalledWith({ path: '/outside/report.pdf' });
    expect(mocks.openFile).not.toHaveBeenCalled();
  });
});
