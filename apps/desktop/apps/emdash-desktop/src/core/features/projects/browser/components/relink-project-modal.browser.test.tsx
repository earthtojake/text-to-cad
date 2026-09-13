import { Dialog } from '@emdash/ui/react/primitives';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { RelinkProjectModal } from './relink-project-modal';

const mocks = vi.hoisted(() => ({
  complete: vi.fn(),
  dismiss: vi.fn(),
  updateProjectConnection: vi.fn(),
}));

vi.mock('@core/features/machines/contributions/app-stores', () => ({
  getMachinesStore: () => ({
    connections: [{ id: 'ssh-2', name: 'Orion' }],
  }),
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  getProjectManagerStore: () => ({
    updateProjectConnection: mocks.updateProjectConnection,
  }),
}));

vi.mock('@core/manifests/browser/modal-api', () => ({
  useModalController: () => ({
    complete: mocks.complete,
    dismiss: mocks.dismiss,
  }),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('RelinkProjectModal', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.complete.mockReset();
    mocks.dismiss.mockReset();
    mocks.updateProjectConnection.mockReset().mockResolvedValue(undefined);
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('relinks to an available Machine through the Project lifecycle', async () => {
    await act(async () => {
      root.render(
        <Dialog.Root open>
          <RelinkProjectModal projectId="project-1" />
        </Dialog.Root>
      );
    });

    expect(host.textContent).toContain('Relink Project');
    expect(host.textContent).toContain('Machine');
    expect(host.textContent).toContain('Orion');
    const machineLabel = host.querySelector('label');
    const machineTrigger = machineLabel?.htmlFor
      ? host.querySelector(`#${CSS.escape(machineLabel.htmlFor)}`)
      : null;
    expect(machineLabel?.textContent).toBe('Machine');
    expect(machineTrigger?.getAttribute('aria-label')).toBe('Relink to Orion');

    const relink = [...host.querySelectorAll('button')].find((button) =>
      button.textContent?.trim().startsWith('Relink')
    );
    expect(relink?.disabled).toBe(false);

    await act(async () => relink?.click());

    expect(mocks.updateProjectConnection).toHaveBeenCalledWith('project-1', 'ssh-2');
    expect(mocks.complete).toHaveBeenCalledOnce();
  });
});
