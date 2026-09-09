import '@emdash/ui/style.css';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { SidebarHeaderActions } from './sidebar-header-actions';

const mocks = vi.hoisted(() => ({
  currentView: 'project' as 'home' | 'project' | 'task',
  projectId: 'project-1' as string | undefined,
  navigate: vi.fn(),
  openProjectFolder: vi.fn(),
}));

vi.mock('@core/features/projects/browser/open-project-folder', () => ({
  useOpenProjectFolder: () => ({
    open: mocks.openProjectFolder,
    busy: false,
  }),
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useWorkspaceSlots: () => ({ currentView: mocks.currentView }),
  useNavigate: () => ({ navigate: mocks.navigate }),
  useViewParams: (definition: { id: string }) =>
    definition.id === 'task'
      ? { projectId: mocks.projectId, taskId: 'task-1' }
      : { projectId: mocks.projectId },
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('SidebarHeaderActions', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.currentView = 'project';
    mocks.projectId = 'project-1';
    mocks.navigate.mockReset();
    mocks.openProjectFolder.mockReset();
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('opens an unpersisted draft in the current project', async () => {
    await act(async () => root.render(<SidebarHeaderActions />));

    const newChat = findButton(host, 'New chat');
    expect(getComputedStyle(newChat).height).toBe('32px');
    await act(async () => newChat.click());

    expect(mocks.navigate).toHaveBeenCalledWith(
      expect.objectContaining({
        viewId: 'home',
        params: expect.objectContaining({ projectId: 'project-1' }),
      })
    );
    expect(mocks.openProjectFolder).not.toHaveBeenCalled();
  });

  it('opens a projectless draft when no project is selected', async () => {
    mocks.currentView = 'home';
    mocks.projectId = undefined;
    await act(async () => root.render(<SidebarHeaderActions />));

    await act(async () => findButton(host, 'New chat').click());

    expect(mocks.navigate).toHaveBeenCalledWith(
      expect.objectContaining({
        viewId: 'home',
        params: expect.objectContaining({ projectId: undefined }),
      })
    );
    expect(mocks.openProjectFolder).not.toHaveBeenCalled();
  });

  it('keeps the selected project when starting over from a draft', async () => {
    mocks.currentView = 'home';
    mocks.projectId = 'project-2';
    await act(async () => root.render(<SidebarHeaderActions />));

    await act(async () => findButton(host, 'New chat').click());

    expect(mocks.navigate).toHaveBeenCalledWith(
      expect.objectContaining({
        viewId: 'home',
        params: expect.objectContaining({ projectId: 'project-2' }),
      })
    );
  });

  it('offers the same two Add project starting points as Codex', async () => {
    await act(async () => root.render(<SidebarHeaderActions />));

    await act(async () => findButton(host, 'Add project').click());
    const existing = Array.from(document.querySelectorAll<HTMLElement>('[role="menuitem"]')).find(
      (item) => item.textContent?.includes('Use an existing folder')
    );
    expect(existing).toBeDefined();
    await act(async () => existing!.click());

    expect(mocks.openProjectFolder).toHaveBeenCalledWith('existing');
  });
});

function findButton(host: HTMLElement, accessibleName: string): HTMLButtonElement {
  const button = Array.from(host.querySelectorAll('button')).find(
    (candidate) =>
      candidate.getAttribute('aria-label') === accessibleName ||
      candidate.textContent?.trim() === accessibleName
  );
  if (!button) throw new Error(`Could not find ${accessibleName} button`);
  return button;
}
