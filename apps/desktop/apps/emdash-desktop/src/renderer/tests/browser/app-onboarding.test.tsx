import type { ReactNode } from 'react';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { App, HAS_SEEN_ONBOARDING } from '@renderer/App';

// Keep the real first-launch routing; isolate unrelated workspace services.
vi.mock('@emdash/ui/react/primitives', () => ({
  Tooltip: { Provider: ({ children }: { children: ReactNode }) => children },
}));
vi.mock('@core/features/github/api/browser/github-context-provider', () => ({
  GithubContextProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@core/features/terminals/browser/pty/pty-pool-provider', () => ({
  TerminalPoolProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@core/features/workbench/contributions/browser/layout-provider', () => ({
  WorkspaceLayoutContextProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@core/primitives/external-links/browser', () => ({
  ExternalLinkProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@renderer/lib/layout/provider', () => ({
  WorkspaceViewProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@renderer/lib/providers/theme-provider', () => ({
  ThemeProvider: ({ children }: { children: ReactNode }) => children,
}));
vi.mock('@core/features/workbench/api/browser/open-external-link', () => ({
  confirmOpenExternalLink: vi.fn(),
}));
vi.mock('@core/features/workbench/browser/window-controls', () => ({
  FramelessTitlebarOverlay: () => <div>Window controls</div>,
}));
vi.mock('@core/services/hosts/browser/recovery-wakeups', () => ({
  HostRecoveryWakeups: () => null,
}));
vi.mock('@renderer/app/app-menu-events', () => ({ AppMenuEvents: () => null }));
vi.mock('@renderer/app/app-shutdown-lifecycle', () => ({ AppShutdownLifecycle: () => null }));
vi.mock('@renderer/lib/modal/modal-renderer', () => ({ ModalRenderer: () => null }));
vi.mock('@renderer/app/welcome', () => ({ WelcomeScreen: () => <div>Welcome to Hardcore</div> }));
vi.mock('@renderer/app/workspace', () => ({ Workspace: () => <div>CAD workspace</div> }));

describe('CAD app first launch', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    (
      globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
    ).IS_REACT_ACT_ENVIRONMENT = true;
    localStorage.removeItem(HAS_SEEN_ONBOARDING);
    localStorage.removeItem('emdash:has-seen-onboarding:v1');
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
    localStorage.removeItem(HAS_SEEN_ONBOARDING);
    localStorage.removeItem('emdash:has-seen-onboarding:v1');
  });

  const render = async () => act(async () => root.render(<App />));

  it('welcomes a fresh user immediately without import discovery or sign-in', async () => {
    await render();
    expect(host.textContent).toContain('Welcome to Hardcore');
    expect(host.textContent).toContain('Window controls');
    expect(host.textContent).not.toContain('Sign in');
    expect(localStorage.getItem(HAS_SEEN_ONBOARDING)).toBe('true');
  });

  it('opens the workspace for returning Hardcore users', async () => {
    localStorage.setItem(HAS_SEEN_ONBOARDING, 'true');
    await render();
    expect(host.textContent).toBe('CAD workspace');
  });

  it('opens the workspace for returning users with the legacy onboarding marker', async () => {
    localStorage.setItem('emdash:has-seen-onboarding:v1', 'true');
    await render();
    expect(host.textContent).toBe('CAD workspace');
    expect(localStorage.getItem(HAS_SEEN_ONBOARDING)).toBe('true');
  });
});
