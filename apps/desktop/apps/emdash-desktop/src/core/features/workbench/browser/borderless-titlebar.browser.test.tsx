import { act, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const layoutState = vi.hoisted(() => ({
  isLeftOpen: false,
  toggleLeftSidebar: vi.fn(),
}));

const historyState = vi.hoisted(() => ({
  canGoBack: true,
  canGoForward: false,
  back: vi.fn(),
  forward: vi.fn(),
}));

vi.mock('@emdash/ui/react/primitives', () => ({
  Button: ({
    variant: _variant,
    size: _size,
    ...props
  }: ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: string;
    size?: string;
  }) => <button {...props} />,
  Tooltip: {
    Root: ({ children }: { children: ReactNode }) => <>{children}</>,
    Trigger: ({ children, render }: { children?: ReactNode; render?: ReactNode }) =>
      render ?? <button type="button">{children}</button>,
    Content: () => null,
  },
}));

vi.mock('@core/features/workbench/browser/window-controls', () => ({
  WindowControls: () => <div data-window-controls />,
}));

vi.mock('@core/features/workbench/contributions/browser/layout-provider', () => ({
  useWorkspaceLayoutContext: () => layoutState,
}));

vi.mock('@core/primitives/keybindings/api', () => ({
  detectPlatformContext: () => ({ os: 'linux' }),
}));

vi.mock('@core/primitives/keybindings/browser/shortcut', () => ({
  BoundShortcut: () => null,
}));

vi.mock('@core/primitives/navigation/browser/navigation-selectors', () => ({
  getNavigation: () => ({ applyEntry: () => true }),
  getNavigationHistory: () => historyState,
}));

import { BorderlessTitlebar } from '@core/features/workbench/contributions/browser/BorderlessTitlebar';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('BorderlessTitlebar', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    layoutState.isLeftOpen = false;
    layoutState.toggleLeftSidebar.mockReset();
    historyState.canGoBack = true;
    historyState.canGoForward = false;
    historyState.back.mockReset();
    historyState.forward.mockReset();
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('shows sidebar recovery and navigation controls when the sidebar is closed', async () => {
    await act(async () => root.render(<BorderlessTitlebar />));

    const showSidebar = host.querySelector<HTMLButtonElement>(
      'button[aria-label="Show left sidebar"]'
    );
    const goBack = host.querySelector<HTMLButtonElement>('button[aria-label="Go back"]');
    const goForward = host.querySelector<HTMLButtonElement>('button[aria-label="Go forward"]');

    expect(showSidebar).not.toBeNull();
    expect(goBack?.disabled).toBe(false);
    expect(goForward?.disabled).toBe(true);
    expect(host.querySelector('button button')).toBeNull();

    await act(async () => showSidebar?.click());
    await act(async () => goBack?.click());

    expect(layoutState.toggleLeftSidebar).toHaveBeenCalledOnce();
    expect(historyState.back).toHaveBeenCalledOnce();
  });

  it('keeps window chrome mounted without duplicating controls when the sidebar is open', async () => {
    layoutState.isLeftOpen = true;
    await act(async () => root.render(<BorderlessTitlebar />));

    expect(host.querySelector('[data-borderless-titlebar]')).not.toBeNull();
    expect(host.querySelector('[data-window-controls]')).not.toBeNull();
    expect(host.querySelectorAll('button')).toHaveLength(0);
  });
});
