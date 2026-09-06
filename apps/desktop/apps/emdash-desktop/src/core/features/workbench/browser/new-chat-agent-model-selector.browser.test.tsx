import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import '@emdash/ui/style.css';
import React, { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import '../../../../renderer/index.css';
import { NewChatAgentModelSelector } from './new-chat-agent-model-selector';

const mocks = vi.hoisted(() => ({
  includeNewRelease: false,
  agents: [
    {
      id: 'codex',
      status: 'available',
      capabilities: {
        acp: { kind: 'supported' },
        models: {
          kind: 'selectable',
          modelOptions: {
            'gpt-5.6-sol': { name: 'GPT-5.6 Sol' },
            'gpt-5.3-codex-spark': { name: 'GPT-5.3 Codex Spark' },
          },
        },
      },
    },
    {
      id: 'claude',
      status: 'available',
      capabilities: {
        acp: { kind: 'supported' },
        models: {
          kind: 'selectable',
          modelOptions: {
            default: { name: 'Default (recommended)' },
            'claude-fable-5': { name: 'Claude Fable 5' },
            'claude-haiku-4-5': { name: 'Claude Haiku 4.5' },
          },
        },
      },
    },
  ],
}));

vi.mock('@core/features/agents/api/browser/use-agents', () => ({
  useAgents: () => ({ data: mocks.agents }),
}));

vi.mock('@core/features/agents/api/browser/client', () => ({
  hostRefFromConnectionId: () => ({ kind: 'local' }),
  getAgentsClient: async () => ({
    discoverModels: async ({ providerId }: { providerId: string }) => ({
      success: true,
      data: Object.entries(
        mocks.agents.find((agent) => agent.id === providerId)!.capabilities.models.modelOptions
      )
        .map(([id, option]) => ({ id, name: option!.name }))
        .concat(mocks.includeNewRelease ? [{ id: 'future-release', name: 'Future release' }] : []),
    }),
  }),
  unwrapAgentsResult: async (result: Promise<{ data: unknown }>) => (await result).data,
}));

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

describe.each(['emlight', 'emdark'] as const)('NewChatAgentModelSelector (%s)', (themeClass) => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    mocks.includeNewRelease = false;
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

  it('discovers a newly released model on refresh without reloading the app', async () => {
    await act(async () =>
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <Harness />
        </QueryClientProvider>
      )
    );
    await act(async () => page.getByRole('button', { name: 'Choose agent and model' }).click());
    await expect.element(page.getByRole('button', { name: 'GPT-5.6 Sol' })).toBeVisible();
    mocks.includeNewRelease = true;
    await act(async () => page.getByRole('button', { name: 'Refresh', exact: true }).click());
    await expect
      .element(page.getByRole('button', { name: 'Future release', exact: true }))
      .toBeVisible();
    await act(async () =>
      page.getByRole('button', { name: 'Future release', exact: true }).click()
    );
    expect(page.getByRole('button', { name: 'Choose agent and model' })).toHaveTextContent(
      /Future release/
    );
  });

  it('offers the provider default and every named model without truncating rows', async () => {
    await act(async () =>
      root.render(
        <QueryClientProvider client={new QueryClient()}>
          <Harness />
        </QueryClientProvider>
      )
    );

    const trigger = page.getByRole('button', { name: 'Choose agent and model' });
    expect(trigger).toHaveTextContent(/Codex.*Default/);

    await act(async () => trigger.click());
    expect(page.getByRole('button', { name: 'Default (recommended)' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect.element(page.getByRole('button', { name: 'GPT-5.6 Sol' })).toBeVisible();
    const longModel = page.getByRole('button', { name: 'GPT-5.3 Codex Spark' });
    expect(longModel).toBeVisible();
    expect(getComputedStyle(longModel.query() as HTMLElement).borderRadius).toBe('8px');
    expect((longModel.query() as HTMLElement).scrollWidth).toBeLessThanOrEqual(
      (longModel.query() as HTMLElement).clientWidth
    );

    await act(async () => page.getByRole('button', { name: 'GPT-5.6 Sol' }).click());
    expect(trigger).toHaveTextContent(/Codex.*GPT-5.6 Sol/);
    await vi.waitFor(() => {
      expect(page.getByRole('button', { name: 'GPT-5.6 Sol' }).query()).toBeNull();
    });

    await act(async () => trigger.click());
    await act(async () => page.getByRole('button', { name: 'Use Claude' }).click());
    expect(trigger).toHaveTextContent(/Claude.*Default/);
    expect(page.getByRole('button', { name: 'Default (recommended)' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect.element(page.getByRole('button', { name: 'Claude Fable 5' })).toBeVisible();
    expect(page.getByRole('button', { name: 'GPT-5.6 Sol' }).query()).toBeNull();
  });
});

function Harness() {
  const [providerId, setProviderId] = useState<'codex' | 'claude'>('codex');
  const [modelId, setModelId] = useState<string | null>(null);

  return (
    <NewChatAgentModelSelector
      providerId={providerId}
      modelId={modelId}
      installedProviderIds={['codex', 'claude']}
      onProviderChange={(provider) => setProviderId(provider as 'codex' | 'claude')}
      onModelChange={setModelId}
    />
  );
}
