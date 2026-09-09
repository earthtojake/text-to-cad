import '@emdash/ui/style.css';
import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { McpDrawer } from '@core/features/mcp/browser/components/McpDrawer';
import { settingsScope } from '@core/features/settings/contributions/scopes';
import { COMMAND_CATALOG } from '@core/manifests/shared/command-catalog';
import { KeybindingService } from '@core/primitives/keybindings/browser/keybinding-service';
import { ThemeProvider } from '@core/primitives/theme/browser/theme-provider';
import type { ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { scopes, type ViewScopeInstance } from '@core/primitives/view-scopes/browser';
import { ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';
import { KeybindingDispatcher } from '@renderer/lib/keybindings/keybinding-dispatcher';

vi.mock('@core/features/agents/contributions/browser/agent-selector', () => ({
  AgentSelector: () => <button type="button">Select agent</button>,
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('MCP drawer Escape routing', () => {
  let host: HTMLDivElement;
  let root: Root;
  let settingsInstance: ViewScopeInstance;
  let detachKeybindings: () => void;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    detachKeybindings?.();
    await act(async () => root.unmount());
    settingsInstance?.dispose();
    host.remove();
  });

  it('closes only the drawer when Escape is pressed inside it', async () => {
    const closeSettings = vi.fn();
    const onOpenChange = vi.fn();
    settingsInstance = scopes.instantiate(settingsScope(), {
      impl: {
        'settings.close': () => ({ execute: closeSettings }),
      } satisfies ViewScopeImpl<typeof settingsScope>,
    });
    scopes.activate(settingsInstance);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService(COMMAND_CATALOG.defs, { os: 'linux' }),
      scopes,
      { os: 'linux' }
    );
    detachKeybindings = dispatcher.attach(window);

    await act(async () => {
      root.render(
        <ThemeProvider theme="emlight" onThemeChange={vi.fn()}>
          <ViewScopeInstanceProvider instance={settingsInstance}>
            <McpDrawer
              open
              mode={{ type: 'add-custom' }}
              host={LOCAL_HOST_REF}
              providers={[]}
              onOpenChange={onOpenChange}
              onSave={vi.fn(async () => undefined)}
            />
          </ViewScopeInstanceProvider>
        </ThemeProvider>
      );
    });

    const sheet = document.querySelector<HTMLElement>('[data-slot="sheet-content"]');
    const input = sheet?.querySelector<HTMLInputElement>('input');
    expect(sheet).not.toBeNull();
    expect(input).not.toBeNull();

    await act(async () => {
      input!.focus();
      input!.dispatchEvent(
        new KeyboardEvent('keydown', {
          key: 'Escape',
          code: 'Escape',
          bubbles: true,
          cancelable: true,
        })
      );
    });

    expect(closeSettings).not.toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledOnce();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
