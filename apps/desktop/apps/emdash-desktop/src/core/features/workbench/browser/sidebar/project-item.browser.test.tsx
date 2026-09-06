import '@emdash/ui/style.css';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { SidebarProjectItem } from './project-item';

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  confirmDeleteProject: vi.fn(),
  toggleProjectExpanded: vi.fn(),
  expandedProjectIds: new Set<string>(['project-1']),
}));

vi.mock('@core/features/machines/contributions/browser/connection-status-dot', () => ({
  ConnectionStatusDot: () => null,
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', async (importOriginal) => ({
  ...(await importOriginal()),
  getProjectHostAccess: () => ({ state: { kind: 'ready' } }),
  getProjectStore: () => ({
    state: 'registered',
    data: { type: 'local' },
    name: 'Hardcore',
  }),
  projectViewKind: () => 'ready',
}));

vi.mock('@core/features/projects/contributions/browser/use-confirm-delete-project', () => ({
  useConfirmDeleteProject: () => mocks.confirmDeleteProject,
}));

vi.mock('@core/features/source-control/api/browser/stores/source-control-selectors', () => ({
  getGitRepositoryStore: () => undefined,
}));

vi.mock('@core/features/tasks/api/browser/task-state/task-selectors', async (importOriginal) => ({
  ...(await importOriginal()),
  taskHostActionAvailability: () => ({ kind: 'enabled' }),
}));

vi.mock('@core/features/workbench/contributions/browser/app-stores', () => ({
  getSidebarStore: () => ({
    expandedProjectIds: mocks.expandedProjectIds,
    toggleProjectExpanded: mocks.toggleProjectExpanded,
  }),
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', async (importOriginal) => ({
  ...(await importOriginal()),
  useNavigate: () => ({ navigate: mocks.navigate }),
  useViewParams: () => undefined,
  useWorkspaceSlots: () => ({ currentView: 'home' }),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('SidebarProjectItem', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.navigate.mockReset();
    mocks.confirmDeleteProject.mockReset();
    mocks.toggleProjectExpanded.mockReset();
    mocks.expandedProjectIds = new Set(['project-1']);
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('uses the project row to expand or collapse chats instead of opening a dashboard', async () => {
    await act(async () => root.render(<SidebarProjectItem projectId="project-1" />));

    await act(async () => findButton(host, 'Collapse chats in Hardcore').click());

    expect(mocks.toggleProjectExpanded).toHaveBeenCalledWith('project-1');
    expect(mocks.navigate).not.toHaveBeenCalled();
  });

  it('opens one draft without toggling the project row', async () => {
    await act(async () => root.render(<SidebarProjectItem projectId="project-1" />));

    await act(async () => findButton(host, 'New chat in Hardcore').click());

    expect(mocks.navigate).toHaveBeenCalledWith(
      expect.objectContaining({
        viewId: 'home',
        params: expect.objectContaining({ projectId: 'project-1' }),
      })
    );
    expect(mocks.toggleProjectExpanded).not.toHaveBeenCalled();
  });

  it('puts project actions before New chat in both visual and keyboard order', async () => {
    await act(async () => root.render(<SidebarProjectItem projectId="project-1" />));

    const actionLabels = Array.from(host.querySelectorAll('button'))
      .map((button) => button.getAttribute('aria-label'))
      .filter(Boolean);

    expect(actionLabels.indexOf('More actions for Hardcore')).toBeLessThan(
      actionLabels.indexOf('New chat in Hardcore')
    );
  });

  it('keeps archive and search management in the secondary project menu', async () => {
    await act(async () => root.render(<SidebarProjectItem projectId="project-1" />));

    await act(async () => {
      findButton(host, 'Collapse chats in Hardcore').dispatchEvent(
        new MouseEvent('contextmenu', { bubbles: true, button: 2, clientX: 20, clientY: 20 })
      );
    });
    const viewAllChats = Array.from(
      document.querySelectorAll<HTMLElement>('[role="menuitem"]')
    ).find((candidate) => candidate.textContent?.trim() === 'View all chats');
    expect(viewAllChats).toBeDefined();

    await act(async () => viewAllChats?.click());

    expect(mocks.navigate).toHaveBeenCalledWith(
      expect.objectContaining({ params: { projectId: 'project-1' } })
    );
    expect(mocks.toggleProjectExpanded).not.toHaveBeenCalled();
  });

  it('shows project management in a visible ellipsis without toggling the project', async () => {
    await act(async () => root.render(<SidebarProjectItem projectId="project-1" />));

    await act(async () => findButton(host, 'More actions for Hardcore').click());

    const menuItems = Array.from(document.querySelectorAll<HTMLElement>('[role="menuitem"]'));
    const viewAllChats = menuItems.find(
      (candidate) => candidate.textContent?.trim() === 'View all chats'
    );
    const removeProject = menuItems.find(
      (candidate) => candidate.textContent?.trim() === 'Remove Project'
    );
    expect(viewAllChats).toBeDefined();
    expect(removeProject).toBeDefined();

    await act(async () => viewAllChats?.click());

    expect(mocks.navigate).toHaveBeenCalledWith(
      expect.objectContaining({ params: { projectId: 'project-1' } })
    );
    expect(mocks.toggleProjectExpanded).not.toHaveBeenCalled();
  });
});

function findButton(host: HTMLElement, accessibleName: string): HTMLButtonElement {
  const button = Array.from(host.querySelectorAll('button')).find(
    (candidate) => candidate.getAttribute('aria-label') === accessibleName
  );
  if (!button) throw new Error(`Could not find ${accessibleName} button`);
  return button;
}
