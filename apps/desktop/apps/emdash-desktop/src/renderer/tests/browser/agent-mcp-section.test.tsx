import { hostRef } from '@emdash/core/primitives/host/api';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { AgentMcpSection } from '@core/features/settings/browser/agents-page/AgentMcpSection';

const navigation = vi.hoisted(() => ({ navigate: vi.fn() }));

vi.mock('@core/features/agents/api/browser/use-agent-mcps', () => ({
  useAgentMcps: () => ({
    servers: [],
    isLoading: false,
    removeServer: vi.fn(),
    removingServerName: null,
  }),
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useNavigate: () => navigation,
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('AgentMcpSection', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    navigation.navigate.mockReset();
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('opens the machine MCP section for a remote agent', async () => {
    const onManage = vi.fn();
    await act(async () => {
      root.render(
        <AgentMcpSection
          agentId="codex"
          host={hostRef('remote', 'machine-1')}
          onManage={onManage}
        />
      );
    });

    const manageButton = Array.from(host.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Manage in Settings')
    );
    expect(manageButton).toBeDefined();

    await act(async () => manageButton!.click());

    expect(onManage).toHaveBeenCalledOnce();
    expect(navigation.navigate).not.toHaveBeenCalled();
  });

  it('hides the manage shortcut when no handler is provided', async () => {
    await act(async () => {
      root.render(<AgentMcpSection agentId="codex" host={hostRef('remote', 'machine-1')} />);
    });

    const manageButton = Array.from(host.querySelectorAll<HTMLButtonElement>('button')).find(
      (button) => button.textContent?.includes('Manage in Settings')
    );
    expect(manageButton).toBeUndefined();
  });
});
