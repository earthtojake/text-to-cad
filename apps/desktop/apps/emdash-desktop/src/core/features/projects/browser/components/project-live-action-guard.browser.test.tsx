import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectLiveActionGuard } from '@core/features/projects/contributions/browser/project-live-action-guard';

const context = vi.hoisted(() => ({ current: undefined as unknown }));
const machines = vi.hoisted(() => ({ current: [] as { id: string; name: string }[] }));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  getProjectStore: () => context.current,
  asAvailableProject: (value: unknown) => value,
}));

vi.mock('@core/features/machines/contributions/app-stores', () => ({
  getMachinesStore: () => ({ connections: machines.current }),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('ProjectLiveActionGuard', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    machines.current = [];
    context.current = {
      project: { type: 'local', id: 'project-1' },
      host: {
        state: {
          kind: 'degraded',
          situation: 'offline',
          recovery: 'automatic',
        },
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

  it('keeps a disabled action visible with a keyboard-reachable shared explanation', async () => {
    await act(async () => {
      root.render(
        <ProjectLiveActionGuard projectId="project-1">
          <button type="button" disabled>
            New terminal
          </button>
        </ProjectLiveActionGuard>
      );
    });

    const action = host.querySelector('button');
    const explanation = host.querySelector('[role="note"]');
    expect(action?.textContent).toBe('New terminal');
    expect(action?.disabled).toBe(true);
    expect(explanation?.getAttribute('tabindex')).toBe('0');
    expect(explanation?.getAttribute('aria-label')).toBe(
      'Live actions are unavailable while this Project is unavailable on this device.'
    );
  });

  it('uses the configured Machine name for an SSH Project', async () => {
    machines.current = [{ id: 'ssh-1', name: 'Orion' }];
    context.current = {
      project: { type: 'ssh', id: 'project-1', connectionId: 'ssh-1' },
      host: {
        state: {
          kind: 'degraded',
          situation: 'offline',
          recovery: 'automatic',
        },
      },
    };

    await act(async () => {
      root.render(
        <ProjectLiveActionGuard projectId="project-1">
          <button type="button" disabled>
            New terminal
          </button>
        </ProjectLiveActionGuard>
      );
    });

    expect(host.querySelector('[role="note"]')?.getAttribute('aria-label')).toBe(
      'Live actions are unavailable while Orion is offline.'
    );
  });
});
