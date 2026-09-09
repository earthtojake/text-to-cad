import { beforeEach, describe, expect, it, vi } from 'vitest';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { openFile } from './open-file';

const mocks = vi.hoisted(() => ({
  getTaskComposition: vi.fn(),
  getNavigation: vi.fn(),
  transition: vi.fn(),
}));

vi.mock('@core/features/tasks/contributions/views', () => ({
  taskViewDef: { id: 'task' },
}));

vi.mock('@core/primitives/navigation/browser/navigation-selectors', () => ({
  getNavigation: mocks.getNavigation,
}));

vi.mock('@core/primitives/telemetry/browser/focus-tracker', () => ({
  focusTracker: { transition: mocks.transition },
}));

vi.mock('./task-composition-selectors', () => ({
  getTaskComposition: mocks.getTaskComposition,
}));

function fakeComposition() {
  return {
    paneLayout: {
      open: vi.fn(),
      groups: [] as Array<{
        paneId: string;
        pane: { resolvedTabs: Array<{ kind: string }> };
      }>,
      setActiveGroup: vi.fn(),
    },
    setFocusedRegion: vi.fn(),
    revealWorkspaceFile: vi.fn(),
  };
}

const CONTEXT = { projectId: 'project-1', taskId: 'task-1' };

describe('openFile placement policy', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getNavigation.mockReturnValue({ currentRef: { viewId: 'other', params: {} } });
  });

  it('opens a pinned tab in the active pane by default and does not reveal', () => {
    const composition = fakeComposition();
    mocks.getTaskComposition.mockReturnValue(composition);

    const opened = openFile(hostFileRefFromNativePath('/repo/src/a.ts'), { context: CONTEXT });

    expect(opened).toBe(true);
    expect(mocks.getTaskComposition).toHaveBeenCalledWith('project-1', 'task-1');
    expect(composition.paneLayout.open).toHaveBeenCalledWith(
      'file',
      { path: '/repo/src/a.ts' },
      { preview: false, target: 'active' }
    );
    expect(mocks.transition).not.toHaveBeenCalled();
    expect(composition.setFocusedRegion).not.toHaveBeenCalled();
    expect(composition.revealWorkspaceFile).not.toHaveBeenCalled();
  });

  it('passes preview and right-pane target through to the pane layout', () => {
    const composition = fakeComposition();
    mocks.getTaskComposition.mockReturnValue(composition);

    openFile(hostFileRefFromNativePath('/repo/src/a.ts'), {
      context: CONTEXT,
      preview: true,
      target: 'right',
    });

    expect(composition.paneLayout.open).toHaveBeenCalledWith(
      'file',
      { path: '/repo/src/a.ts' },
      { preview: true, target: 'right' }
    );
  });

  it('opens the first artifact to the right of chat', () => {
    const composition = fakeComposition();
    composition.paneLayout.groups = [
      { paneId: 'chat-pane', pane: { resolvedTabs: [{ kind: 'acp-chat' }] } },
    ];
    mocks.getTaskComposition.mockReturnValue(composition);

    openFile(hostFileRefFromNativePath('/repo/models/bracket.step'), {
      context: CONTEXT,
      target: 'artifact',
    });

    expect(composition.paneLayout.setActiveGroup).toHaveBeenCalledWith('chat-pane');
    expect(composition.paneLayout.open).toHaveBeenCalledWith(
      'cad',
      { path: '/repo/models/bracket.step' },
      { preview: false, target: 'right' }
    );
  });

  it('reuses the existing artifact pane even after focus moved', () => {
    const composition = fakeComposition();
    composition.paneLayout.groups = [
      { paneId: 'chat-pane', pane: { resolvedTabs: [{ kind: 'acp-chat' }] } },
      { paneId: 'artifact-pane', pane: { resolvedTabs: [{ kind: 'cad' }] } },
    ];
    mocks.getTaskComposition.mockReturnValue(composition);

    openFile(hostFileRefFromNativePath('/repo/drawings/bracket.svg'), {
      context: CONTEXT,
      target: 'artifact',
    });

    expect(composition.paneLayout.setActiveGroup).not.toHaveBeenCalled();
    expect(composition.paneLayout.open).toHaveBeenCalledWith(
      'file',
      { path: '/repo/drawings/bracket.svg' },
      { preview: false, target: { paneId: 'artifact-pane' } }
    );
  });

  it.each(['/repo/models/bracket.step', '/repo/models/bracket.step.py'])(
    'opens %s in the first-class CAD tab',
    (path) => {
      const composition = fakeComposition();
      mocks.getTaskComposition.mockReturnValue(composition);

      openFile(hostFileRefFromNativePath(path), { context: CONTEXT });

      expect(composition.paneLayout.open).toHaveBeenCalledWith(
        'cad',
        { path },
        { preview: false, target: 'active' }
      );
    }
  );

  it('reveal moves focus to the editor and reveals the file in the sidebar', () => {
    const composition = fakeComposition();
    mocks.getTaskComposition.mockReturnValue(composition);

    openFile(hostFileRefFromNativePath('/repo/src/a.ts'), { context: CONTEXT, reveal: true });

    expect(mocks.transition).toHaveBeenCalledWith({ mainPanel: 'editor' }, 'panel_switch');
    expect(composition.setFocusedRegion).toHaveBeenCalledWith('main');
    expect(composition.revealWorkspaceFile).toHaveBeenCalledWith('/repo/src/a.ts');
  });

  it('defaults the context to the focused task view', () => {
    const composition = fakeComposition();
    mocks.getTaskComposition.mockReturnValue(composition);
    mocks.getNavigation.mockReturnValue({
      currentRef: { viewId: 'task', params: { projectId: 'project-9', taskId: 'task-9' } },
    });

    const opened = openFile(hostFileRefFromNativePath('/repo/src/a.ts'));

    expect(opened).toBe(true);
    expect(mocks.getTaskComposition).toHaveBeenCalledWith('project-9', 'task-9');
  });

  it('returns false when no task view is focused and no context is given', () => {
    const opened = openFile(hostFileRefFromNativePath('/repo/src/a.ts'));

    expect(opened).toBe(false);
    expect(mocks.getTaskComposition).not.toHaveBeenCalled();
  });

  it('returns false when the context resolves to no composition', () => {
    mocks.getTaskComposition.mockReturnValue(undefined);

    const opened = openFile(hostFileRefFromNativePath('/repo/src/a.ts'), { context: CONTEXT });

    expect(opened).toBe(false);
  });
});
