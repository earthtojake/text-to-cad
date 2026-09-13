import '@emdash/ui/style.css';
import React, { act, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import '../../index.css';

const layoutStorage = {
  getItem: vi.fn(() => null),
  setItem: vi.fn(),
  deleteEntry: vi.fn(),
};

const layoutState = { isLeftOpen: true };

const paneGroups = [
  {
    paneId: 'chat',
    pane: { resolvedTabs: [{ kind: 'acp-chat' }], entries: new Map() },
  },
  {
    paneId: 'artifact',
    pane: { resolvedTabs: [{ kind: 'cad' }], entries: new Map() },
  },
];

const taskView = {
  chrome: { commands: { collapseSidebar: vi.fn() } },
  isSidebarCollapsed: false,
  isTerminalDrawerOpen: false,
  paneLayout: {
    groups: paneGroups,
    setActiveGroup: vi.fn(),
    splitRight: vi.fn(),
  },
  sidebarTab: 'files',
  space: { isHydrated: true },
};

vi.mock('@core/features/workbench/contributions/browser/layout-provider', () => ({
  useWorkspaceLayoutContext: () => ({
    isLeftOpen: layoutState.isLeftOpen,
    isZenActive: false,
    layoutKey: 'layout-test',
    layoutStorage,
    toggleLeftSidebar: vi.fn(),
  }),
}));

vi.mock('@core/features/tasks/contributions/browser/task-view-context', () => ({
  useTaskViewContext: () => ({ projectId: 'project-1', taskId: 'task-1' }),
}));

vi.mock('@core/features/tasks/api/browser/task-state/task-selectors', () => ({
  getTaskManagerStore: () => undefined,
  getTaskStore: () => ({ data: {}, state: 'ready' }),
  taskViewKind: () => 'ready',
  taskHostActionAvailability: () => ({ kind: 'enabled' }),
  taskErrorMessage: () => '',
}));

vi.mock('@core/features/workbench/api/browser/task-composition-context', () => ({
  useTaskComposition: () => taskView,
}));

vi.mock('@core/features/workbench/api/browser/task-tab-registry', () => ({
  taskTabView: {
    TabLayoutProvider: ({ children }: { children: ReactNode }) => children,
  },
}));

vi.mock('@core/manifests/browser/project-availability-ui', () => ({
  projectAvailabilityUi: {
    Boundary: ({ children }: { children: ReactNode }) => children,
  },
}));

vi.mock('@core/features/cad/contributions/browser/cad-task-run-lifecycle', () => ({
  CadTaskRunLifecycle: () => null,
}));

vi.mock('@core/features/terminals/contributions/browser/task-terminal/terminal-panel', () => ({
  TerminalsPanel: () => null,
}));

vi.mock('@core/primitives/mementos/browser', () => ({
  createLayoutStorage: () => layoutStorage,
}));

vi.mock('@core/features/workbench/contributions/browser/tabs/pane-provider', () => ({
  PaneProvider: ({ group, children }: { group: { paneId: string }; children: ReactNode }) => (
    <section data-layout-panel={group.paneId} className="h-full min-w-0 overflow-hidden">
      {children}
    </section>
  ),
}));

vi.mock('@core/primitives/workbench-shell/browser/tabs/pane-content', () => ({
  PaneContent: () => <div className="h-full w-full" />,
}));

vi.mock('@core/features/tasks/browser/view/task-sidebar', () => ({
  TaskSidebar: () => <aside data-layout-panel="files" className="h-full w-full overflow-hidden" />,
}));

import { TaskMainPanel } from '@core/features/tasks/browser/main-panel';
import { WorkspaceContentLayout, WorkspaceLayout } from '@renderer/lib/layout/workspace-layout';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('workspace layout width matrix', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    layoutState.isLeftOpen = true;
    document.documentElement.style.height = '100%';
    document.body.style.height = '100%';
    document.body.style.margin = '0';
    host = document.createElement('div');
    host.style.width = '100vw';
    host.style.height = '100vh';
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it.each([
    { width: 700, threadsOpen: false },
    { width: 800, threadsOpen: true },
    { width: 960, threadsOpen: true },
    { width: 1200, threadsOpen: true },
  ])(
    'keeps the supported workspace panels ordered without overlap at $width px',
    async ({ width, threadsOpen }) => {
      // Four open panels cannot satisfy the product's current 180 + 200 +
      // 200 + 280px resize floors at 700px. The supported compact state
      // closes Threads, just as the titlebar Threads toggle does.
      layoutState.isLeftOpen = threadsOpen;
      await page.viewport(width, 720);
      await act(async () => {
        root.render(
          <WorkspaceLayout
            leftSidebar={
              <nav data-layout-panel="threads" className="h-full w-full overflow-hidden" />
            }
            mainContent={
              <WorkspaceContentLayout
                titlebarSlot={<header className="h-10" />}
                mainPanel={<TaskMainPanel />}
              />
            }
          />
        );
      });

      await new Promise((resolve) => requestAnimationFrame(() => resolve(undefined)));

      const expectedPanels = threadsOpen
        ? ['threads', 'chat', 'artifact', 'files']
        : ['chat', 'artifact', 'files'];
      const panels = expectedPanels.map((name) => {
        const element = host.querySelector<HTMLElement>(`[data-layout-panel="${name}"]`);
        expect(element, `${name} panel should render`).not.toBeNull();
        return { name, rect: element!.getBoundingClientRect() };
      });

      const hostRect = host.getBoundingClientRect();
      for (const { name, rect } of panels) {
        expect(rect.width, `${name} should retain usable width`).toBeGreaterThanOrEqual(140);
        expect(rect.left, `${name} should stay inside the workspace`).toBeGreaterThanOrEqual(
          hostRect.left - 1
        );
        expect(rect.right, `${name} should stay inside the workspace`).toBeLessThanOrEqual(
          hostRect.right + 1
        );
      }

      const threads = host.querySelector('[data-layout-panel="threads"]');
      if (threadsOpen) expect(threads).not.toBeNull();
      else expect(threads).toBeNull();

      for (let index = 1; index < panels.length; index += 1) {
        expect(
          panels[index - 1]!.rect.right,
          `${panels[index - 1]!.name} should not overlap ${panels[index]!.name}`
        ).toBeLessThanOrEqual(panels[index]!.rect.left + 1);
      }

      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(width);
    }
  );
});
