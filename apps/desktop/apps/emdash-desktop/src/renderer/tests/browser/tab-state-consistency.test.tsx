import { DndContext } from '@dnd-kit/core';
import '@emdash/ui/style.css';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { CadWorkspaceModeBar } from '@core/features/cad/browser/cad-workspace-mode-bar';
import type { TabHost } from '@core/primitives/workbench-shell/browser/tabs/core/tab-host';
import type {
  ResolvedTab,
  TabResource,
  TabViewContext,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import { PaneContext } from '@core/primitives/workbench-shell/browser/tabs/pane-context';
import type { PaneStore } from '@core/primitives/workbench-shell/browser/tabs/pane-store';
import { GenericTabItem } from '@core/primitives/workbench-shell/browser/tabs/tab-bar/generic-tab-item';
import '../../index.css';
import '../../design-system.css';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

const context: TabViewContext = { viewId: 'tab-state-test' };
const resource: TabResource = { dispose: vi.fn() };
const tab: ResolvedTab = {
  tabId: 'file:fuzzy-breads-flow.step.py',
  kind: 'file',
  isPreview: false,
  isActive: true,
  resource,
};

function createHost(): TabHost {
  return {
    resolvedTabs: [tab],
    resolvedActiveTabId: tab.tabId,
    ctx: context,
    openKind: vi.fn(),
    setActiveTab: vi.fn(),
    pin: vi.fn(),
    closeTab: vi.fn(),
    requestCloseTab: vi.fn(),
    closeOthers: vi.fn(),
    signalActivateIntent: vi.fn(),
    renameRequest: null,
    requestRename: vi.fn(),
    clearRenameRequest: vi.fn(),
    commitRename: vi.fn(),
  };
}

describe.each(['emlight', 'emdark'] as const)('tab state consistency (%s)', (themeClass) => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    document.documentElement.classList.add(themeClass);
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    document.documentElement.classList.remove(themeClass);
    host.remove();
  });

  it('keeps an active file tab flat until interaction while preserving mode selection', async () => {
    const tabHost = createHost();
    const pane = {
      focusActiveContent: vi.fn(),
    } as unknown as PaneStore;

    await act(async () => {
      root.render(
        <div className={`${themeClass} surface-paper`}>
          <button type="button" data-testid="focus-start">
            Focus start
          </button>
          <DndContext>
            <PaneContext.Provider
              value={{
                paneId: 'pane-1',
                pane,
                scopeInstance: undefined,
                isFocusedPane: true,
              }}
            >
              <div className="flex h-10 items-center">
                <GenericTabItem
                  tab={tab}
                  host={tabHost}
                  ctx={context}
                  label="fuzzy-breads-flow.step.py"
                />
              </div>
            </PaneContext.Provider>
          </DndContext>

          <CadWorkspaceModeBar
            modes={['3d', 'drawing', 'source']}
            activeMode="3d"
            onChange={vi.fn()}
          />
        </div>
      );
    });

    const fileTab = host.querySelector<HTMLElement>(`[data-tabid="${tab.tabId}"]`)!;
    expect(getComputedStyle(fileTab).backgroundColor).toBe('rgba(0, 0, 0, 0)');
    expect(getComputedStyle(fileTab).borderRadius).toBe('8px');

    const fileTabLabel = page.getByText('fuzzy-breads-flow.step.py');
    await fileTabLabel.hover();
    await expect.poll(() => getComputedStyle(fileTab).backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
    expect(getComputedStyle(fileTab).borderRadius).toBe('8px');

    const modelTab = page.getByRole('tab', { name: '3D' });
    const drawingTab = page.getByRole('tab', { name: 'Drawing' });
    await fileTabLabel.unhover();
    const focusStart = page.getByTestId('focus-start').query() as HTMLButtonElement;
    focusStart.focus();
    for (let index = 0; index < 4 && document.activeElement !== fileTab; index += 1) {
      await userEvent.tab();
    }
    expect(document.activeElement).toBe(fileTab);
    expect(fileTab.matches(':focus-visible')).toBe(true);
    await expect.poll(() => getComputedStyle(fileTab).backgroundColor).not.toBe('rgba(0, 0, 0, 0)');
    expect(getComputedStyle(fileTab).borderRadius).toBe('8px');

    expect(modelTab).toHaveAttribute('aria-selected', 'true');
    expect(drawingTab).toHaveAttribute('aria-selected', 'false');
    expect(getComputedStyle(modelTab.query() as HTMLElement).backgroundColor).not.toBe(
      'rgba(0, 0, 0, 0)'
    );
    expect(getComputedStyle(drawingTab.query() as HTMLElement).backgroundColor).toBe(
      'rgba(0, 0, 0, 0)'
    );
  });
});
