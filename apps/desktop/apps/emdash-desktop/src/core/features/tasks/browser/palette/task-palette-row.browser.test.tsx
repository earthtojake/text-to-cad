import { Command } from 'cmdk';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { TaskStore } from '@core/features/tasks/api/browser/stores/task-store';
import { TaskPaletteRow } from './task-palette-row';

const state = vi.hoisted(() => ({
  navigate: vi.fn(),
  openConversation: vi.fn(),
  taskStore: undefined as TaskStore | undefined,
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useNavigate: () => ({ navigate: state.navigate }),
}));

vi.mock('@core/features/tasks/api/browser/task-state/task-selectors', () => ({
  getTaskStore: () => state.taskStore,
}));

vi.mock('@core/features/conversations/api/browser/conversation-selectors', () => ({
  taskAgentStatus: () => 'completed',
}));

vi.mock('@core/features/conversations/api/browser/stores/conversation-registry', () => ({
  conversationRegistry: { get: () => undefined },
}));

vi.mock('@core/features/workbench/api/browser/task-composition-selectors', () => ({
  getTaskComposition: () => ({
    paneLayout: { open: state.openConversation },
  }),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('TaskPaletteRow', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    state.navigate.mockReset();
    state.openConversation.mockReset();
    state.taskStore = {
      data: { id: 'task-1', name: 'Fix login' },
    } as TaskStore;
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('renders task status and preserves task navigation behavior', () => {
    const onSelect = vi.fn();

    act(() => {
      root.render(
        <Command>
          <TaskPaletteRow
            value="tasks:task-1"
            onSelect={onSelect}
            match={{
              id: 'typed:task:project-1:task-1',
              title: 'Fix login',
              relevance: { band: 'exact', score: 1 },
              target: { kind: 'task', projectId: 'project-1', taskId: 'task-1' },
            }}
          />
        </Command>
      );
    });

    expect(container.querySelector('[data-status="completed"]')).not.toBeNull();
    act(() => {
      container.querySelector<HTMLElement>('[cmdk-item]')!.click();
    });

    expect(onSelect).toHaveBeenCalledOnce();
    expect(state.navigate).toHaveBeenCalledWith(
      expect.objectContaining({
        viewId: 'task',
        params: { projectId: 'project-1', taskId: 'task-1' },
      })
    );
  });

  it('opens a current-task conversation without navigating away', () => {
    const onSelect = vi.fn();

    act(() => {
      root.render(
        <Command>
          <TaskPaletteRow
            value="tasks:conversation-1"
            onSelect={onSelect}
            match={{
              id: 'notification:conversation:conversation-1',
              title: 'Finished work',
              section: 'Notifications',
              relevance: { band: 'exact', score: 1 },
              target: {
                kind: 'conversation',
                projectId: 'project-1',
                taskId: 'task-1',
                conversationId: 'conversation-1',
                keepCurrentTask: true,
              },
            }}
          />
        </Command>
      );
    });

    act(() => {
      container.querySelector<HTMLElement>('[cmdk-item]')!.click();
    });

    expect(state.openConversation).toHaveBeenCalledWith(
      'conversation',
      { conversationId: 'conversation-1' },
      { preview: false }
    );
    expect(onSelect).toHaveBeenCalledOnce();
    expect(state.navigate).not.toHaveBeenCalled();
  });
});
