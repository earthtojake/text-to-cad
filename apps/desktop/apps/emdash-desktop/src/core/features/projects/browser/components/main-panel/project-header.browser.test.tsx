import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectHeader } from './project-header';

const mocks = vi.hoisted(() => ({
  confirmDeleteProject: vi.fn(),
}));

const state = vi.hoisted(() => ({
  project: {
    type: 'local' as 'local' | 'ssh',
    id: 'project-1',
    name: 'Emdash',
    path: '/repos/emdash',
    baseRef: 'main',
    repositoryWorkspaceId: null,
    createdAt: '2026-08-14T00:00:00.000Z',
    updatedAt: '2026-08-14T00:00:00.000Z',
    connectionId: undefined as string | undefined,
  },
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  getProjectStore: () => ({ data: state.project, name: state.project.name }),
  projectDisplayName: () => state.project.name,
}));

vi.mock('@core/features/projects/contributions/browser/use-confirm-delete-project', () => ({
  useConfirmDeleteProject: () => mocks.confirmDeleteProject,
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('ProjectHeader', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.confirmDeleteProject.mockReset();
    state.project.type = 'local';
    state.project.connectionId = undefined;
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    document.body.querySelectorAll('[role="menu"]').forEach((menu) => menu.remove());
    host.remove();
  });

  it('shows local project identity without repository chrome and preserves remove', async () => {
    await act(async () => root.render(<ProjectHeader projectId="project-1" />));

    expect(host.querySelector('h1')?.textContent).toBe('Emdash');
    const identityIcon = host.querySelector('[data-severity="neutral"]');
    expect(identityIcon?.querySelector('.lucide-folder-open')).not.toBeNull();
    expect(host.querySelector('.lucide-folder-input')).toBeNull();

    expect(host.textContent).not.toContain('emdash-ai/emdash');
    expect(host.querySelector('[aria-label="Open In"]')).toBeNull();

    const actions = host.querySelector<HTMLButtonElement>('[aria-label="Project actions"]');
    await act(async () => actions?.click());
    const remove = [...document.querySelectorAll<HTMLElement>('[role="menuitem"]')].find(
      (item) => item.textContent === 'Remove project'
    );
    await act(async () => remove?.click());
    expect(mocks.confirmDeleteProject).toHaveBeenCalledWith({
      projectId: 'project-1',
      projectLabel: 'Emdash',
    });
  });

  it('uses the remote project icon without exposing transport controls', async () => {
    state.project.type = 'ssh';
    state.project.connectionId = 'machine-1';

    await act(async () => root.render(<ProjectHeader projectId="project-1" />));

    const identityIcon = host.querySelector('[data-severity="neutral"]');
    expect(identityIcon?.querySelector('.lucide-folder-input')).not.toBeNull();
    expect(host.querySelector('.lucide-folder-open')).toBeNull();
    expect(host.querySelector('[aria-label="Open In"]')).toBeNull();
  });
});
