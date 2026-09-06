import { openFixture } from '@tooling/utils/db';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createConversationRegistry } from '@core/features/conversations/api/node/registry';
import { linkConversationToTask } from './link-conversation-to-task';

/**
 * "Link into a task" (spec §8) is a client registry annotation: it rewrites the row's
 * link columns and never touches host state.
 */
describe('linkConversationToTask', () => {
  let fixture: Awaited<ReturnType<typeof openFixture>>;

  beforeEach(async () => {
    fixture = await openFixture('empty');
  });

  afterEach(() => {
    fixture.close();
  });

  function seedProjectAndTask(suffix: string): { projectId: string; taskId: string } {
    const projectId = `project-${suffix}`;
    const taskId = `task-${suffix}`;
    fixture.sqlite
      .prepare(`INSERT INTO projects (id, name) VALUES (?, ?)`)
      .run(projectId, `Project ${suffix}`);
    fixture.sqlite
      .prepare(`INSERT INTO tasks (id, project_id, name, status) VALUES (?, ?, ?, 'running')`)
      .run(taskId, projectId, `Task ${suffix}`);
    return { projectId, taskId };
  }

  function seedOrphan(id: string): void {
    createConversationRegistry(fixture.db).register({
      id,
      projectId: null,
      taskId: null,
      title: `Conversation ${id}`,
      provider: 'claude',
      type: 'acp',
      location: 'local',
      sshConnectionId: null,
    });
  }

  it('annotates the registry row so the conversation appears on the task', async () => {
    const { projectId, taskId } = seedProjectAndTask('a');
    seedOrphan('conv-1');

    await linkConversationToTask(fixture.db, { conversationId: 'conv-1', projectId, taskId });

    expect(createConversationRegistry(fixture.db).getLive('conv-1')).toMatchObject({
      projectId,
      taskId,
    });
  });

  it('re-links an already-linked conversation to the new task', async () => {
    const first = seedProjectAndTask('a');
    const second = seedProjectAndTask('b');
    seedOrphan('conv-1');
    await linkConversationToTask(fixture.db, { conversationId: 'conv-1', ...first });

    await linkConversationToTask(fixture.db, { conversationId: 'conv-1', ...second });

    expect(createConversationRegistry(fixture.db).getLive('conv-1')).toMatchObject({
      projectId: second.projectId,
      taskId: second.taskId,
    });
  });

  it('rejects links to absent or mismatched tasks and absent conversations', async () => {
    const { projectId, taskId } = seedProjectAndTask('a');
    const other = seedProjectAndTask('b');
    seedOrphan('conv-1');

    await expect(
      linkConversationToTask(fixture.db, { conversationId: 'conv-absent', projectId, taskId })
    ).rejects.toThrow('was not found');
    await expect(
      linkConversationToTask(fixture.db, {
        conversationId: 'conv-1',
        projectId,
        taskId: other.taskId,
      })
    ).rejects.toThrow('was not found in project');
    expect(createConversationRegistry(fixture.db).getLive('conv-1')).toMatchObject({
      projectId: null,
      taskId: null,
    });
  });
});
