import { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { ProjectContextErrorPanel, ProjectMainPanel } from './main-panel';

const panelState = vi.hoisted(() => ({
  kind: 'ready',
  store: {
    id: 'project-1',
    name: 'Emdash',
    context: undefined as
      | undefined
      | {
          kind: 'failed';
          error: {
            type: 'context-initialization-failed';
            stage: 'memento';
            message: string;
          };
        },
  },
}));

vi.mock('@core/features/projects/api/browser/stores/project-selectors', () => ({
  getProjectManagerStore: () => ({ hydrateProjectContext: vi.fn() }),
  getProjectStore: () => panelState.store,
  projectDisplayName: () => 'Emdash',
  projectViewKind: () => panelState.kind,
}));

vi.mock('@core/features/projects/contributions/browser/use-confirm-delete-project', () => ({
  useConfirmDeleteProject: () => vi.fn(),
}));

vi.mock('@core/features/workbench/contributions/browser/BorderlessTitlebar', () => ({
  BorderlessTitlebar: () => <header data-borderless-titlebar />,
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useCurrentViewParams: () => ({ params: { projectId: 'project-1' } }),
  useNavigate: () => ({ navigate: vi.fn() }),
}));

vi.mock('./project-header', () => ({
  ProjectHeader: () => <header data-layout-part="header">Emdash</header>,
}));

vi.mock('@core/features/projects/contributions/browser/project-availability-boundary', () => ({
  ProjectAvailabilityBoundary: ({ children }: { children: ReactNode }) => (
    <>
      <section role="status" data-layout-part="banner">
        Offline
      </section>
      {children}
    </>
  ),
}));

vi.mock('./active-project', () => ({
  ActiveProject: () => (
    <>
      <nav data-layout-part="tabs">Tabs</nav>
      <main data-layout-part="panel">Panel</main>
    </>
  ),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('ProjectContextErrorPanel', () => {
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

  it('offers desktop context Retry and Remove Project actions only', async () => {
    const onRetry = vi.fn();
    const onRemove = vi.fn();
    await act(async () => {
      root.render(
        <ProjectContextErrorPanel
          error={{
            type: 'context-initialization-failed',
            stage: 'memento',
            message: 'raw internal failure',
          }}
          onRetry={onRetry}
          onRemove={onRemove}
        />
      );
    });

    const buttons = Array.from(host.querySelectorAll('button'));
    expect(buttons.map((button) => button.textContent)).toEqual(['Retry', 'Remove Project']);
    expect(host.textContent).not.toContain('Connect');
    expect(host.textContent).not.toContain('raw internal failure');

    await act(async () => buttons[0]?.click());
    await act(async () => buttons[1]?.click());
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onRemove).toHaveBeenCalledOnce();
  });
});

describe('ProjectMainPanel layout', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    panelState.kind = 'ready';
    panelState.store.context = undefined;
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('scrolls one page in header, banner, tabs, and panel order', async () => {
    await act(async () => root.render(<ProjectMainPanel />));

    const scroller = host.querySelector('[data-project-page-scroll]');
    expect(scroller?.classList.contains('overflow-y-auto')).toBe(true);
    expect(host.querySelector('[data-borderless-titlebar]')).not.toBeNull();
    expect(
      [...host.querySelectorAll('[data-layout-part]')].map((element) =>
        element.getAttribute('data-layout-part')
      )
    ).toEqual(['header', 'banner', 'tabs', 'panel']);
  });

  it.each([
    ['hydrating', 'Loading project'],
    ['context_error', 'Could not load Project'],
  ])('retains in-page Project identity for the %s state', async (kind, message) => {
    panelState.kind = kind;
    panelState.store.context =
      kind === 'context_error'
        ? {
            kind: 'failed',
            error: {
              type: 'context-initialization-failed',
              stage: 'memento',
              message: 'raw internal failure',
            },
          }
        : undefined;

    await act(async () => root.render(<ProjectMainPanel />));

    expect(host.querySelector('[data-layout-part="header"]')?.textContent).toBe('Emdash');
    expect(host.textContent).toContain(message);
    expect(host.querySelector('[data-project-page-scroll]')).not.toBeNull();
  });
});
