import { act, type ComponentType, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const navigationMocks = vi.hoisted(() => ({
  useWorkspaceSlots: vi.fn(),
}));

vi.mock('@core/features/workbench/browser/sidebar/left-sidebar', () => ({
  LeftSidebar: () => null,
}));
vi.mock('@core/features/workbench/browser/window-scope', () => ({
  WindowScope: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useWorkspaceSlots: navigationMocks.useWorkspaceSlots,
  useWorkspaceViewParams: () => ({ params: {} }),
}));
vi.mock('@core/primitives/theme/browser', () => ({ useTheme: () => undefined }));
vi.mock('@renderer/lib/keybindings', () => ({
  BrowserShortcutForwarding: () => null,
  KeybindingDispatcherMount: () => null,
}));
vi.mock('@renderer/lib/layout/workspace-layout', () => ({
  WorkspaceLayout: ({ mainContent }: { mainContent: ReactNode }) => mainContent,
  WorkspaceContentLayout: ({
    titlebarSlot,
    mainPanel,
  }: {
    titlebarSlot: ReactNode;
    mainPanel: ReactNode;
  }) => (
    <>
      {titlebarSlot}
      {mainPanel}
    </>
  ),
}));
vi.mock('@emdash/ui/react/primitives', () => ({ Toaster: () => null }));

import { Workspace } from '@renderer/app/workspace';

type TestSlots = {
  WrapView: ComponentType<{ children: ReactNode }>;
  TitlebarSlot: ComponentType;
  MainPanel: ComponentType;
  currentView: string;
};

function slotsFor(view: string): TestSlots {
  return {
    WrapView: ({ children }) => <section data-wrapper={view}>{children}</section>,
    TitlebarSlot: () => <header data-titlebar={view} />,
    MainPanel: () => <main data-main={view} />,
    currentView: view,
  };
}

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('Workspace active view composition', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
    navigationMocks.useWorkspaceSlots.mockReset();
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('renders the wrapper and slots from one navigation snapshot', async () => {
    navigationMocks.useWorkspaceSlots
      .mockReturnValueOnce(slotsFor('project'))
      .mockReturnValue(slotsFor('task'));

    await act(async () => root.render(<Workspace />));

    expect(host.querySelector('[data-wrapper="project"]')).not.toBeNull();
    expect(host.querySelector('[data-titlebar="project"]')).not.toBeNull();
    expect(host.querySelector('[data-main="project"]')).not.toBeNull();
    expect(navigationMocks.useWorkspaceSlots).toHaveBeenCalledOnce();
  });
});
