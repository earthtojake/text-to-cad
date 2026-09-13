import { Command } from 'cmdk';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { createProjectPaletteProvider } from './project-palette-provider';

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  asAvailableProject: () => undefined,
  getProjectManagerStore: () => {
    throw new Error('Idle project inventory is not used by this test');
  },
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useNavigate: () => ({ navigate: mocks.navigate }),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('project palette row', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.append(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
    vi.clearAllMocks();
  });

  it('preserves project presentation, dismissal, and navigation', async () => {
    const provider = createProjectPaletteProvider({
      search: async () => [],
      idle: () => [],
    });
    const Row = provider.render;
    const onSelect = vi.fn();

    await act(async () => {
      root.render(
        <Command shouldFilter={false}>
          <Command.List>
            <Row
              match={{
                id: 'project-1',
                title: 'Emdash',
                subtitle: '/repos/emdash',
                relevance: { band: 'exact', score: 1 },
              }}
              value="projects:project-1"
              onSelect={onSelect}
            />
          </Command.List>
        </Command>
      );
    });

    const row = host.querySelector<HTMLElement>('[cmdk-item]');
    expect(row?.textContent).toContain('Emdash');
    expect(row?.textContent).toContain('/repos/emdash');
    expect(row?.querySelector('svg')).not.toBeNull();

    await act(async () => row?.click());

    expect(onSelect).toHaveBeenCalledOnce();
    expect(mocks.navigate).toHaveBeenCalledWith(projectViewDef({ projectId: 'project-1' }));
    expect(onSelect.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.navigate.mock.invocationCallOrder[0] ?? Number.POSITIVE_INFINITY
    );
  });
});
