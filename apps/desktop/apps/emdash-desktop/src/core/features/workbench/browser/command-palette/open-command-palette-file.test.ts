import { beforeEach, describe, expect, it, vi } from 'vitest';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { openCommandPaletteFile } from './open-command-palette-file';

const mocks = vi.hoisted(() => ({
  openFileInTaskEditor: vi.fn(),
}));

vi.mock('@core/features/editor/api/browser/open-file-in-file-editor', () => ({
  openFileInTaskEditor: mocks.openFileInTaskEditor,
}));

describe('openCommandPaletteFile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens the selected workspace file and navigates to its task', () => {
    const dismiss = vi.fn();
    const navigate = vi.fn();

    openCommandPaletteFile(
      {
        id: '/repo/src/command-k.ts',
        projectId: 'project-1',
        taskId: 'task-1',
      },
      dismiss,
      navigate
    );

    expect(mocks.openFileInTaskEditor).toHaveBeenCalledWith(
      'project-1',
      'task-1',
      '/repo/src/command-k.ts'
    );
    expect(dismiss).toHaveBeenCalledOnce();
    expect(navigate).toHaveBeenCalledWith(
      taskViewDef({ projectId: 'project-1', taskId: 'task-1' })
    );
  });

  it('ignores file results without a task identity', () => {
    const dismiss = vi.fn();
    const navigate = vi.fn();

    openCommandPaletteFile(
      {
        id: '/repo/src/command-k.ts',
        projectId: null,
        taskId: null,
      },
      dismiss,
      navigate
    );

    expect(mocks.openFileInTaskEditor).not.toHaveBeenCalled();
    expect(dismiss).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });
});
