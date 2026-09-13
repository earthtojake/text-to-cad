import { describe, expect, it, vi } from 'vitest';
import type { CreateTaskParams } from '@core/primitives/tasks/api';
import { startBlankChat, type StartBlankChatDependencies } from './start-blank-chat';

function setup(options: { existingTitles?: string[]; workspaceId?: string | null } = {}) {
  const ids = ['task-1', 'conversation-1'];
  const createTask = vi.fn(async (_params: unknown) => {});
  const loadTasks = vi.fn(async () => {});
  const navigate = vi.fn();
  const tasks = new Map(
    (options.existingTitles ?? []).map((name, index) => [`existing-${index}`, { data: { name } }])
  );
  const workspaceId = 'workspaceId' in options ? options.workspaceId : 'workspace-1';
  const dependencies = {
    getProject: () => ({ repositoryWorkspaceId: workspaceId }),
    getTaskManager: () => ({ tasks, createTask, loadTasks }),
    createId: () => ids.shift()!,
    navigate,
  } as unknown as StartBlankChatDependencies;

  return { createTask, loadTasks, navigate, dependencies };
}

describe('startBlankChat', () => {
  it('creates an initial ACP conversation in the project workspace and navigates to it', async () => {
    const { createTask, loadTasks, navigate, dependencies } = setup();

    await expect(
      startBlankChat(
        {
          projectId: 'project-1',
          providerId: 'codex',
          autoApprove: true,
        },
        dependencies
      )
    ).resolves.toEqual({ taskId: 'task-1', conversationId: 'conversation-1' });

    expect(loadTasks).toHaveBeenCalledTimes(1);
    expect(createTask).toHaveBeenCalledWith({
      id: 'task-1',
      projectId: 'project-1',
      taskConfig: {
        version: '1',
        name: 'New chat',
        initialConversation: {
          id: 'conversation-1',
          provider: 'codex',
          title: 'New chat',
          autoApprove: true,
          type: 'acp',
        },
      },
      workspaceConfig: {
        version: '2',
        git: { kind: 'none' },
        workspace: { kind: 'repository-instance', workspaceId: 'workspace-1' },
      },
    });
    expect(navigate).toHaveBeenCalledWith('project-1', 'task-1');
  });

  it('gives simultaneous unsent chats distinct placeholder titles', async () => {
    const { createTask, dependencies } = setup({
      existingTitles: ['New chat', 'new chat 2'],
    });

    await startBlankChat(
      { projectId: 'project-1', providerId: 'claude', autoApprove: false },
      dependencies
    );

    const created = createTask.mock.calls[0]?.[0] as CreateTaskParams | undefined;
    expect(created?.taskConfig).toMatchObject({
      name: 'New chat 3',
      initialConversation: { title: 'New chat 3' },
    });
  });

  it('creates and queues the first message atomically from the draft composer', async () => {
    const { createTask, dependencies } = setup();

    await startBlankChat(
      {
        projectId: 'project-1',
        providerId: 'codex',
        autoApprove: false,
        initialPrompt: '  Make a mounting bracket  ',
      },
      dependencies
    );

    const created = createTask.mock.calls[0]?.[0] as CreateTaskParams | undefined;
    expect(created?.taskConfig.initialConversation).toMatchObject({
      initialQueue: [
        {
          text: 'Make a mounting bracket',
          hiddenContext: expect.stringContaining('CAD-first'),
        },
      ],
    });
  });

  it('stores an explicit model while leaving the provider default unset', async () => {
    const explicit = setup();
    await startBlankChat(
      {
        projectId: 'project-1',
        providerId: 'codex',
        autoApprove: false,
        modelId: 'gpt-5.6-sol',
      },
      explicit.dependencies
    );

    const explicitTask = explicit.createTask.mock.calls[0]?.[0] as CreateTaskParams | undefined;
    expect(explicitTask?.taskConfig.initialConversation).toMatchObject({
      model: 'gpt-5.6-sol',
    });

    const providerDefault = setup();
    await startBlankChat(
      {
        projectId: 'project-1',
        providerId: 'codex',
        autoApprove: false,
      },
      providerDefault.dependencies
    );

    const defaultTask = providerDefault.createTask.mock.calls[0]?.[0] as
      | CreateTaskParams
      | undefined;
    expect(defaultTask?.taskConfig.initialConversation).not.toHaveProperty('model');
  });

  it('keeps the draft mounted until task creation succeeds', async () => {
    const { createTask, navigate, dependencies } = setup();
    let rejectCreation!: (error: Error) => void;
    createTask.mockImplementation(
      async () =>
        await new Promise<void>((_resolve, reject) => {
          rejectCreation = reject;
        })
    );

    const creation = startBlankChat(
      {
        projectId: 'project-1',
        providerId: 'codex',
        autoApprove: false,
        initialPrompt: 'Make a bracket',
      },
      dependencies
    );
    await vi.waitFor(() => expect(createTask).toHaveBeenCalledOnce());
    expect(navigate).not.toHaveBeenCalled();

    rejectCreation(new Error('create failed'));
    await expect(creation).rejects.toThrow('create failed');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('does not create an orphan chat before the project workspace is ready', async () => {
    const { createTask, navigate, dependencies } = setup({ workspaceId: null });

    await expect(
      startBlankChat(
        { projectId: 'project-1', providerId: 'codex', autoApprove: false },
        dependencies
      )
    ).rejects.toThrow('still opening');

    expect(createTask).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });
});
