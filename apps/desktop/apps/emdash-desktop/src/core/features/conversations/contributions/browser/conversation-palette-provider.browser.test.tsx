import { Command } from 'cmdk';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import {
  conversationPaletteProviderDef,
  conversationsPaletteProviderDefs,
} from './conversation-palette-provider';
import type { ConversationPaletteMatch } from './conversation-palette-source';

const mocks = vi.hoisted(() => ({
  getConversationManager: vi.fn(),
  getTaskComposition: vi.fn(),
  navigate: vi.fn(),
}));

vi.mock('@emdash/ui/react/components', () => ({
  AgentStatus: ({ status }: { status: string | null }) => (
    <span data-agent-status={status ?? 'none'} />
  ),
}));

vi.mock('mobx-react-lite', () => ({
  observer: <T,>(component: T) => component,
}));

vi.mock('@core/features/agents/contributions/browser/agent-icon', () => ({
  AgentIcon: ({ id }: { id: string }) => <span data-agent-id={id} />,
}));

vi.mock('@core/features/conversations/api/browser/stores/conversation-registry', () => ({
  conversationRegistry: { get: mocks.getConversationManager },
}));

vi.mock('@core/features/workbench/api/browser/task-composition-selectors', () => ({
  getTaskComposition: mocks.getTaskComposition,
}));

vi.mock('@core/primitives/navigation/browser/navigation-hooks', () => ({
  useNavigate: () => ({ navigate: mocks.navigate }),
}));

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('ConversationPaletteProviderRow', () => {
  let host: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.clearAllMocks();
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
  });

  it('contributes @conversations with one-character search enabled', () => {
    expect(conversationPaletteProviderDef).toMatchObject({
      kind: 'conversations',
      keyword: '@conversations',
      minQueryLength: 1,
    });
    expect(conversationsPaletteProviderDefs).toEqual([conversationPaletteProviderDef]);
  });

  it('preserves conversation presentation, status, opening, and task navigation', async () => {
    const open = vi.fn();
    const onSelect = vi.fn();
    const conversation = {
      data: {
        id: 'conversation-1',
        providerId: 'claude',
        title: 'claude (2)',
      },
      indicatorStatus: 'working',
    };
    mocks.getConversationManager.mockReturnValue({
      conversations: new Map([['conversation-1', conversation]]),
    });
    mocks.getTaskComposition.mockReturnValue({ paneLayout: { open } });
    const match: ConversationPaletteMatch = {
      id: 'conversation-1',
      title: 'claude (2)',
      relevance: { band: 'exact', score: 1, contextAffinity: 1 },
      item: {
        kind: 'conversation',
        id: 'conversation-1',
        projectId: 'project-1',
        taskId: 'task-1',
        title: 'claude (2)',
        subtitle: '',
        score: 0,
      },
    };
    const Row = conversationPaletteProviderDef.render;

    await act(async () => {
      root.render(
        <Command>
          <Command.List>
            <Row match={match} value="conversations:conversation-1" onSelect={onSelect} />
          </Command.List>
        </Command>
      );
    });

    expect(host.textContent).toContain('Claude (2)');
    expect(host.querySelector('[data-agent-id="claude"]')).not.toBeNull();
    expect(host.querySelector('[data-agent-status="working"]')).not.toBeNull();

    await act(async () => {
      host.querySelector<HTMLElement>('[cmdk-item]')?.click();
    });

    expect(open).toHaveBeenCalledWith(
      'conversation',
      { conversationId: 'conversation-1' },
      { preview: false }
    );
    expect(onSelect).toHaveBeenCalledOnce();
    expect(mocks.navigate).toHaveBeenCalledWith(
      taskViewDef({ projectId: 'project-1', taskId: 'task-1' })
    );
    expect(open.mock.invocationCallOrder[0]).toBeLessThan(onSelect.mock.invocationCallOrder[0]!);
    expect(onSelect.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.navigate.mock.invocationCallOrder[0]!
    );
  });
});
