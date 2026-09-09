import { beforeEach, describe, expect, it, vi } from 'vitest';

type TaskCreatedHandler = (
  task: { id: string; projectId: string },
  params: {
    workspaceConfig: { git: { kind: string } };
    taskConfig: {
      linkedIssue?: { provider: 'linear' };
      initialConversation?: {
        provider: 'claude-code';
        initialPrompt?: string;
        initialQueue?: Array<{ text: string }>;
      };
    };
  }
) => void;

type TaskProvisionedHandler = (info: { projectId: string; taskId: string }) => void;

const mocks = vi.hoisted(() => ({
  capture: vi.fn(),
  taskServiceOn: vi.fn(),
  taskSessionOn: vi.fn(),
}));

const { installTaskTelemetry } = await import('./task-telemetry');
installTaskTelemetry(
  { capture: mocks.capture } as never,
  { on: mocks.taskServiceOn } as never,
  { hooks: { on: mocks.taskSessionOn } } as never
);

function getTaskCreatedHandler() {
  return mocks.taskServiceOn.mock.calls.find(([event]) => event === 'task:created')?.[1] as
    | TaskCreatedHandler
    | undefined;
}

function getTaskProvisionedHandler() {
  return mocks.taskSessionOn.mock.calls.find(([event]) => event === 'task:provisioned')?.[1] as
    | TaskProvisionedHandler
    | undefined;
}

describe('task telemetry', () => {
  beforeEach(() => {
    mocks.capture.mockClear();
  });

  it('registers task lifecycle listeners when loaded', () => {
    expect(getTaskCreatedHandler()).toBeTypeOf('function');
    expect(getTaskProvisionedHandler()).toBeTypeOf('function');
  });

  it('captures task creation and linked issue properties', () => {
    const handler = getTaskCreatedHandler();
    expect(handler).toBeTypeOf('function');

    handler?.(
      { id: 'task-1', projectId: 'project-1' },
      {
        workspaceConfig: { git: { kind: 'new-branch' } },
        taskConfig: {
          linkedIssue: { provider: 'linear' },
          initialConversation: {
            provider: 'claude-code',
            initialQueue: [{ text: 'Investigate ENG-1876' }],
          },
        },
      }
    );

    expect(mocks.capture).toHaveBeenNthCalledWith(1, 'task_created', {
      strategy: 'issue',
      has_initial_prompt: true,
      has_issue: 'linear',
      provider: 'claude-code',
      project_id: 'project-1',
      task_id: 'task-1',
    });
    expect(mocks.capture).toHaveBeenNthCalledWith(2, 'issue_linked_to_task', {
      provider: 'linear',
      project_id: 'project-1',
      task_id: 'task-1',
    });
  });

  it('captures task provisioning', () => {
    const handler = getTaskProvisionedHandler();
    expect(handler).toBeTypeOf('function');

    handler?.({ projectId: 'project-1', taskId: 'task-1' });

    expect(mocks.capture).toHaveBeenCalledWith('task_provisioned', {
      project_id: 'project-1',
      task_id: 'task-1',
    });
  });
});
