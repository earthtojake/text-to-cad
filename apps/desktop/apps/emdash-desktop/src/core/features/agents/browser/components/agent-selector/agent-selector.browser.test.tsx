import '@emdash/ui/style.css';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { AgentSelector } from '@core/features/agents/contributions/browser/agent-selector';

vi.mock(
  '@core/features/agents/api/browser/components/agent-selector/use-agent-availability',
  () => ({
    useAgentAvailability: () => ({
      groups: [
        {
          value: 'installed',
          label: 'Installed',
          items: [
            {
              value: 'codex',
              label: 'Codex',
              agentId: 'codex',
              disabled: false,
              canInstall: false,
              supportsAcp: true,
            },
            {
              value: 'claude',
              label: 'Claude Code',
              agentId: 'claude',
              disabled: false,
              canInstall: false,
              supportsAcp: true,
            },
          ],
        },
        {
          value: 'not-installed',
          label: 'Not installed',
          items: [
            {
              value: 'grok',
              label: 'Grok',
              agentId: 'grok',
              disabled: true,
              canInstall: true,
              supportsAcp: false,
            },
          ],
        },
      ],
    }),
  })
);

vi.mock('@core/features/agents/browser/components/agent-selector/agent-info-card', async () => {
  const { createElement } = await import('react');
  return {
    AgentInfoCard: ({ id }: { id: string }) =>
      createElement('div', { 'data-testid': 'agent-details' }, `Details for ${id}`),
  };
});

vi.mock('@core/features/agents/contributions/browser/agent-icon', async () => {
  const { createElement } = await import('react');
  return {
    AgentIcon: ({ id }: { id: string }) =>
      createElement('span', { 'aria-hidden': true, 'data-agent-icon': id }),
  };
});

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('AgentSelector', () => {
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

  it('shows agent details when an uninstalled agent is hovered', async () => {
    await act(async () => {
      root.render(<AgentSelector value="codex" onChange={vi.fn()} />);
    });

    const trigger = host.querySelector<HTMLElement>('[data-slot="combobox-trigger"]');
    expect(trigger).not.toBeNull();
    await act(async () => trigger!.click());

    const uninstalledAgent = page.getByRole('option', { name: 'Grok' });
    const uninstalledAgentElement = uninstalledAgent.element();
    expect(uninstalledAgentElement.hasAttribute('data-disabled')).toBe(true);
    expect(getComputedStyle(uninstalledAgentElement).pointerEvents).toBe('auto');

    await uninstalledAgent.hover();

    await vi.waitFor(
      () => {
        expect(document.body.textContent).toContain('Details for grok');
      },
      { timeout: 2_000 }
    );
  });

  it('can render a simplified allowlisted picker', async () => {
    await act(async () => {
      root.render(
        <AgentSelector
          value="codex"
          onChange={vi.fn()}
          allowedAgentIds={['codex', 'claude']}
          agentLabelOverrides={{ claude: 'Claude' }}
          simplified
        />
      );
    });

    const trigger = host.querySelector<HTMLElement>('[data-slot="combobox-trigger"]');
    expect(trigger).not.toBeNull();
    await act(async () => trigger!.click());

    expect(page.getByRole('option', { name: 'Codex' })).toBeVisible();
    expect(page.getByRole('option', { name: 'Claude' })).toBeVisible();
    expect(page.getByRole('option', { name: 'Grok' }).query()).toBeNull();
    expect(page.getByPlaceholder('Search agents...').query()).toBeNull();
    expect(document.body.textContent).not.toContain('Chat UI');
    expect(document.body.textContent).not.toContain('Installed');
  });
});
