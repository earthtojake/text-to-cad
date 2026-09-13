import { ok } from '@emdash/shared';
import { deferred } from '@emdash/shared/testing';
import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ProjectHostAccessState } from '@core/features/projects/api/browser/stores/project-context';
import type { LocalProject, SshProject } from '@core/primitives/projects/api';
import {
  ProjectAvailabilityBanner,
  ProjectAvailabilityFrame,
  type ProjectAvailabilityActionHandlers,
} from './project-availability-banner';

const localProject: LocalProject = {
  type: 'local',
  id: 'local-project',
  name: 'Local Project',
  path: '/project',
  baseRef: 'main',
  repositoryWorkspaceId: null,
  createdAt: '2026-08-13T00:00:00.000Z',
  updatedAt: '2026-08-13T00:00:00.000Z',
};

const sshProject: SshProject = {
  type: 'ssh',
  id: 'ssh-project',
  name: 'SSH Project',
  path: '/project',
  baseRef: 'main',
  connectionId: 'ssh-1',
  repositoryWorkspaceId: null,
  createdAt: '2026-08-13T00:00:00.000Z',
  updatedAt: '2026-08-13T00:00:00.000Z',
};

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('ProjectAvailabilityBanner', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  async function render(
    project: LocalProject | SshProject,
    state: ProjectHostAccessState,
    children?: ReactNode,
    actionHandlers: ProjectAvailabilityActionHandlers = {
      retry: async () => ok<void>(),
      connect: async () => ok<void>(),
      diagnostics: async () => ok<void>(),
    }
  ): Promise<void> {
    await act(async () => {
      root.render(
        children ? (
          <ProjectAvailabilityFrame
            project={project}
            state={state}
            machineName="Orion"
            actionHandlers={actionHandlers}
          >
            {children}
          </ProjectAvailabilityFrame>
        ) : (
          <ProjectAvailabilityBanner
            project={project}
            state={state}
            machineName="Orion"
            actionHandlers={actionHandlers}
          />
        )
      );
    });
  }

  it('offers only Retry for local runtime recovery', async () => {
    const recover = vi.fn(async () => ok<void>());
    await render(
      localProject,
      { kind: 'degraded', situation: 'offline', recovery: 'automatic' },
      undefined,
      { retry: recover }
    );

    const status = host.querySelector('[role="status"]');
    expect(status?.getAttribute('aria-live')).toBe('polite');
    expect(status?.textContent).toContain('Local runtime is unavailable');
    expect(status?.textContent).toContain('Project data remains available');
    expect(status?.textContent).not.toContain('Connect');
    expect(status?.textContent).not.toContain('Open Machines');

    const retry = status?.querySelector('button');
    expect(retry?.textContent).toBe('Retry');
    await act(async () => retry?.click());
    expect(recover).toHaveBeenCalledOnce();
  });

  it('uses the SSH Machine name and keeps the banner above Project content', async () => {
    await render(
      sshProject,
      { kind: 'degraded', situation: 'offline', recovery: 'automatic' },
      <main data-testid="project-content">Project navigation and tabs</main>
    );

    const status = host.querySelector('[role="status"]');
    const content = host.querySelector('[data-testid="project-content"]');
    expect(status?.textContent).toContain('Orion is offline');
    expect(status?.querySelector('button')?.textContent).toBe('Connect');
    expect(status?.compareDocumentPosition(content!)).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  });

  it.each([
    ['connecting', 'Connecting to Orion', 'Open Machines'],
    ['provisioning', 'Preparing Orion', 'Open Machines'],
    ['handshaking', 'Preparing Orion', 'Open Machines'],
    ['attaching', 'Opening Project on Orion', null],
  ] as const)('announces %s progress politely', async (state, title, actionLabel) => {
    await render(sshProject, {
      kind: 'degraded',
      situation: state,
      recovery: 'automatic',
    });

    const status = host.querySelector('[role="status"]');
    expect(status?.textContent).toContain(title);
    expect(status?.getAttribute('aria-live')).toBe('polite');
    const action = status?.querySelector('button');
    expect(action?.textContent ?? null).toBe(actionLabel);
  });

  it('shows automatic recovery progress with an explicit Retry now action', async () => {
    await render(sshProject, {
      kind: 'degraded',
      situation: 'recovering',
      recovery: 'automatic',
      issue: {
        type: 'host-unavailable',
        host: { type: 'remote', id: 'private-connection-id' },
        reason: 'connection-failed',
        message: 'raw connection failure',
      },
      nextAttemptAt: 12_000,
    });

    const status = host.querySelector('[role="status"]');
    expect(status?.textContent).toContain('Could not connect to Orion');
    expect(status?.textContent).toContain('Automatic recovery will continue');
    expect(status?.textContent).not.toContain('private-connection-id');
    expect(status?.textContent).not.toContain('raw connection failure');
    const retry = [...(status?.querySelectorAll('button') ?? [])].find(
      (button) => button.textContent === 'Retry now'
    );
    expect(retry?.textContent).toBe('Retry now');
    expect(retry?.getAttribute('aria-disabled')).toBe('false');
    expect(status?.textContent).toContain('Open Machines');
  });

  it('announces exhausted automatic recovery as a manual Retry', async () => {
    await render(sshProject, {
      kind: 'degraded',
      situation: 'attention',
      recovery: 'manual',
      issue: {
        type: 'host-unavailable',
        host: { type: 'remote', id: 'ssh-1' },
        reason: 'runtime-unavailable',
        message: 'raw runtime failure',
      },
    });

    const alert = host.querySelector('[role="alert"]');
    expect(alert?.textContent).toContain('Automatic recovery stopped');
    const retry = alert?.querySelector('button');
    expect(retry?.textContent).toBe('Retry');
    expect(retry?.getAttribute('aria-disabled')).toBe('false');
  });

  it('does not claim six attempts for an immediately manual recovery outcome', async () => {
    await render(sshProject, {
      kind: 'degraded',
      situation: 'attention',
      recovery: 'manual',
      issue: {
        type: 'repository-unavailable',
        path: '/private/repository',
        message: 'raw filesystem failure',
      },
    });

    const alert = host.querySelector('[role="alert"]');
    expect(alert?.textContent).not.toContain('six attempts');
    expect(alert?.textContent).not.toContain('/private/repository');
    expect(alert?.textContent).not.toContain('raw filesystem failure');
  });

  it('renders and dispatches both Host identity corrective actions', async () => {
    const relink = vi.fn();
    const remove = vi.fn();
    await render(
      sshProject,
      {
        kind: 'degraded',
        situation: 'attention',
        recovery: 'blocked',
        issue: {
          type: 'host-identity-lost',
          host: { type: 'remote', id: 'deleted-connection-id' },
          message: 'raw identity failure',
        },
      },
      undefined,
      { 'relink-project': relink, 'remove-project': remove }
    );

    const alert = host.querySelector('[role="alert"]');
    expect(alert?.textContent).toContain('This Project is no longer linked to a Machine');
    expect(alert?.textContent).not.toContain('deleted-connection-id');
    const buttons = [...(alert?.querySelectorAll('button') ?? [])];
    const relinkButton = buttons.find((button) => button.textContent === 'Relink Project');
    const removeButton = buttons.find((button) => button.textContent === 'Remove Project');
    expect(relinkButton?.getAttribute('aria-disabled')).toBe('false');
    expect(removeButton?.getAttribute('aria-disabled')).toBe('false');
    await act(async () => relinkButton?.click());
    await act(async () => removeButton?.click());
    expect(relink).toHaveBeenCalledOnce();
    expect(remove).toHaveBeenCalledOnce();
  });

  it('keeps focus and joins repeated clicks while recovery is acknowledged', async () => {
    const request = deferred<ReturnType<typeof ok<void>>>();
    const recover = vi.fn(() => request.promise);
    await render(
      sshProject,
      { kind: 'degraded', situation: 'offline', recovery: 'automatic' },
      undefined,
      { connect: recover }
    );
    const button = host.querySelector('button');
    button?.focus();

    await act(async () => {
      button?.click();
      button?.click();
    });

    expect(recover).toHaveBeenCalledOnce();
    expect(document.activeElement).toBe(button);
    expect(button?.getAttribute('aria-disabled')).toBe('true');
    const descriptionId = button?.getAttribute('aria-describedby');
    expect(descriptionId).toBeTruthy();
    expect(host.querySelector(`#${descriptionId}`)?.textContent).toContain('already in progress');
    expect(host.querySelector('[role="status"]')?.textContent).toContain('Orion is offline');

    request.resolve(ok<void>());
    await act(async () => await request.promise);

    expect(host.querySelector('button')?.getAttribute('aria-disabled')).toBe('false');
  });

  it('renders no banner or reserved space when Host access is ready', async () => {
    await render(sshProject, { kind: 'ready', hostGeneration: 2 });

    expect(host.querySelector('[role="status"]')).toBeNull();
    expect(host.textContent).toBe('');
  });
});
