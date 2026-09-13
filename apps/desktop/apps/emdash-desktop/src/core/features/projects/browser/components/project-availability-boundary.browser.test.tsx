import { hostRef } from '@emdash/core/primitives/host/api';
import { runtimeHostUnavailable } from '@emdash/core/primitives/runtime-resolution/api';
import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectAvailabilityBoundary } from '@core/features/projects/contributions/browser/project-availability-boundary';

const mocks = vi.hoisted(() => ({
  confirmDeleteProject: vi.fn(),
  navigate: vi.fn(),
  openRelinkProject: vi.fn(),
  recover: vi.fn(),
}));
const context = vi.hoisted(() => ({ current: undefined as unknown }));

vi.mock('@core/features/machines/contributions/app-stores', () => ({
  getMachinesStore: () => ({ connections: [] }),
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  asAvailableProject: (value: unknown) => value,
  getProjectStore: () => context.current,
}));

vi.mock('@core/features/projects/contributions/browser/use-confirm-delete-project', () => ({
  useConfirmDeleteProject: () => mocks.confirmDeleteProject,
}));

vi.mock('@core/manifests/browser/modal-api', () => ({
  useOpenModal: () => mocks.openRelinkProject,
}));

vi.mock('@core/features/updates/contributions/app-stores', () => ({
  getUpdateStore: () => ({ check: vi.fn() }),
}));

vi.mock('@core/features/settings/contributions/views', () => ({
  settingsViewDef: (params: unknown) => ({ id: 'settings', params }),
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useNavigate: () => ({ navigate: mocks.navigate }),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('ProjectAvailabilityBoundary', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.confirmDeleteProject.mockReset();
    mocks.navigate.mockReset();
    mocks.openRelinkProject.mockReset();
    mocks.recover.mockReset();
    context.current = {
      project: {
        type: 'ssh',
        id: 'project-1',
        name: 'Review Project',
        path: '/project',
        baseRef: 'main',
        connectionId: 'deleted-connection-id',
        repositoryWorkspaceId: null,
        createdAt: '2026-08-13T00:00:00.000Z',
        updatedAt: '2026-08-13T00:00:00.000Z',
      },
      host: {
        state: {
          kind: 'degraded',
          situation: 'attention',
          recovery: 'blocked',
          issue: {
            type: 'host-identity-lost',
            host: { type: 'remote', id: 'deleted-connection-id' },
            message: 'raw identity failure',
          },
        },
        recover: mocks.recover,
      },
    };
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('wires both Host identity recovery actions without leaving the Project shell', async () => {
    await act(async () => {
      root.render(
        <ProjectAvailabilityBoundary projectId="project-1">
          <main>Project shell</main>
        </ProjectAvailabilityBoundary>
      );
    });

    const buttons = [...host.querySelectorAll('button')];
    const relink = buttons.find((button) => button.textContent === 'Relink Project');
    const remove = buttons.find((button) => button.textContent === 'Remove Project');

    expect(relink?.getAttribute('aria-disabled')).toBe('false');
    expect(remove?.getAttribute('aria-disabled')).toBe('false');
    expect(host.textContent).toContain('Project shell');

    await act(async () => relink?.click());
    expect(mocks.openRelinkProject).toHaveBeenCalledWith({ projectId: 'project-1' });
    expect(mocks.navigate).not.toHaveBeenCalled();

    await act(async () => remove?.click());
    expect(mocks.confirmDeleteProject).toHaveBeenCalledWith({
      projectId: 'project-1',
      projectLabel: 'Review Project',
    });
  });

  it('places an inline availability banner directly before Project page content', async () => {
    await act(async () => {
      root.render(
        <ProjectAvailabilityBoundary projectId="project-1" layout="inline">
          <main>Project shell</main>
        </ProjectAvailabilityBoundary>
      );
    });

    const banner = host.querySelector<HTMLElement>('[role="alert"]');
    expect(banner).not.toBeNull();
    expect(banner?.nextElementSibling?.textContent).toBe('Project shell');
  });

  it('keeps inline Project content mounted while availability changes', async () => {
    const lifecycle = { mounts: 0, unmounts: 0 };
    const projectContext = context.current as {
      host: {
        state:
          | { kind: 'ready'; hostGeneration: number }
          | {
              kind: 'degraded';
              situation: 'offline';
              recovery: 'automatic';
            };
      };
    };
    projectContext.host.state = { kind: 'ready', hostGeneration: 1 };

    function ProjectShell() {
      useEffect(() => {
        lifecycle.mounts += 1;
        return () => {
          lifecycle.unmounts += 1;
        };
      }, []);
      return <main>Project shell</main>;
    }

    await act(async () => {
      root.render(
        <ProjectAvailabilityBoundary projectId="project-1" layout="inline">
          <ProjectShell />
        </ProjectAvailabilityBoundary>
      );
    });
    projectContext.host.state = {
      kind: 'degraded',
      situation: 'offline',
      recovery: 'automatic',
    };
    await act(async () => {
      root.render(
        <ProjectAvailabilityBoundary projectId="project-1" layout="inline">
          <ProjectShell />
        </ProjectAvailabilityBoundary>
      );
    });

    expect(host.textContent).toContain('Project shell');
    expect(lifecycle).toEqual({ mounts: 1, unmounts: 0 });
  });

  it('routes local runtime correction to System settings without SSH actions', async () => {
    context.current = {
      project: {
        type: 'local',
        id: 'project-1',
        name: 'Local Project',
        path: '/project',
        baseRef: 'main',
        repositoryWorkspaceId: null,
        createdAt: '2026-08-13T00:00:00.000Z',
        updatedAt: '2026-08-13T00:00:00.000Z',
      },
      host: {
        state: {
          kind: 'degraded',
          situation: 'attention',
          recovery: 'blocked',
          issue: runtimeHostUnavailable(
            hostRef('local', 'local'),
            'unsupported-platform',
            'raw local runtime message'
          ),
        },
        recover: mocks.recover,
      },
    };

    await act(async () => {
      root.render(
        <ProjectAvailabilityBoundary projectId="project-1">
          <main>Project shell</main>
        </ProjectAvailabilityBoundary>
      );
    });

    expect(host.textContent).toContain('This platform is not supported');
    expect(host.textContent).not.toMatch(/Open Machines|Connect/);
    const openDiagnostics = [...host.querySelectorAll('button')].find(
      (button) => button.textContent === 'Open Diagnostics'
    );
    expect(openDiagnostics?.getAttribute('aria-disabled')).toBe('false');
    await act(async () => openDiagnostics?.click());

    expect(mocks.navigate).toHaveBeenCalledWith({
      id: 'settings',
      params: { tab: 'system' },
    });
  });
});
