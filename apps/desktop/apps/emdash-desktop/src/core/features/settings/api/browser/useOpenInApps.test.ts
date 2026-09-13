import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { UseOpenInAppsResult } from './useOpenInApps';

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

const mocks = vi.hoisted(() => ({
  checkInstalledApps: vi.fn(),
  getPlatform: vi.fn(),
}));

vi.mock('@core/features/settings/api/browser/use-app-settings-key', () => ({
  useAppSettingsKey: () => ({
    value: { hidden: [] },
    update: vi.fn(),
    isLoading: false,
  }),
}));

vi.mock('@core/primitives/desktop-host/browser/host-client', () => ({
  getHostClient: async () => ({
    checkInstalledApps: mocks.checkInstalledApps,
    getPlatform: mocks.getPlatform,
  }),
}));

const { useOpenInApps } = await import('./useOpenInApps');

async function flushQueries(): Promise<void> {
  await Promise.resolve();
  await new Promise<void>((resolve) => setTimeout(resolve, 0));
  await Promise.resolve();
}

describe('useOpenInApps', () => {
  let dom: JSDOM;
  let root: Root;
  let container: HTMLDivElement;
  let queryClient: QueryClient;
  let latest: UseOpenInAppsResult | null;

  function Probe() {
    latest = useOpenInApps();
    return null;
  }

  beforeEach(() => {
    latest = null;
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>');
    vi.stubGlobal('window', dom.window);
    vi.stubGlobal('document', dom.window.document);
    vi.stubGlobal('HTMLElement', dom.window.HTMLElement);
    container = dom.window.document.getElementById('root') as HTMLDivElement;
    root = createRoot(container);
  });

  afterEach(async () => {
    await queryClient.cancelQueries();
    await act(async () => {
      await flushQueries();
      root.unmount();
    });
    vi.unstubAllGlobals();
    vi.clearAllMocks();
    queryClient.clear();
    dom.window.close();
  });

  it('does not expose macOS-only apps before the platform query resolves', async () => {
    mocks.getPlatform.mockReturnValue(new Promise(() => {}));
    mocks.checkInstalledApps.mockReturnValue(new Promise(() => {}));

    await act(async () => {
      root.render(
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(Probe)
        )
      );
    });

    expect(latest?.loading).toBe(true);
    expect(latest?.installedApps).toEqual([]);
    expect(latest?.labels.finder).toBeUndefined();
  });

  it('uses resolved Windows labels and filters out macOS-only apps', async () => {
    mocks.getPlatform.mockResolvedValue('win32');
    mocks.checkInstalledApps.mockResolvedValue({
      cursor: true,
      finder: true,
      terminal: true,
      xcode: false,
    });

    await act(async () => {
      root.render(
        React.createElement(
          QueryClientProvider,
          { client: queryClient },
          React.createElement(Probe)
        )
      );
    });

    await act(async () => {
      await flushQueries();
    });

    expect(latest?.platform).toBe('win32');
    expect(latest?.labels.finder).toBe('Explorer');
    expect(latest?.installedApps.map((app) => app.id)).toEqual(
      expect.arrayContaining(['finder', 'terminal', 'cursor'])
    );
    expect(latest?.installedApps.map((app) => app.id)).not.toContain('xcode');
  });
});
