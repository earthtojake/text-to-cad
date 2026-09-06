import { DEFAULT_THEME } from '@core/theme';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { createChatContext } from '@/chat-context';
import { createChatView } from '@/chat-view';
import type { ChatCommands, ChatItem, MentionProvider, TranscriptTurn } from '@/index';
import { createChatState } from '@/state/chat-state';

const nextPaint = (): Promise<void> =>
  new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));

const cleanups: Array<() => void> = [];

afterEach(() => {
  for (const cleanup of cleanups.splice(0)) cleanup();
});

function mount(items: ChatItem[], commands: ChatCommands, mentionProvider?: MentionProvider) {
  const context = createChatContext({ theme: DEFAULT_THEME, mentionProvider });
  const state = createChatState(context);
  const turn: TranscriptTurn = {
    id: 'turn-1',
    seq: 0,
    initiator: 'agent',
    items: items.map((item, seq) => ({ ...item, seq })) as TranscriptTurn['items'],
  };
  state.transcript.history.seed([turn]);

  const host = document.createElement('div');
  host.style.cssText = 'position:fixed;top:0;left:0;width:800px;height:700px;';
  document.body.appendChild(host);
  const view = createChatView({ context, state, parent: host, commands });

  cleanups.push(() => {
    view.dispose();
    state.dispose();
    context.dispose();
    host.remove();
  });
  return host;
}

/** Observe whether chat-ui cancelled navigation, then cancel it before the browser acts. */
function dispatchLinkClick(target: HTMLElement): boolean {
  let preventedByChatUi = false;
  const safetyNet = (event: MouseEvent) => {
    preventedByChatUi = event.defaultPrevented;
    event.preventDefault();
  };
  window.addEventListener('click', safetyNet, { once: true });
  target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  return preventedByChatUi;
}

function clickableRowForPath(host: HTMLElement, path: string): HTMLElement {
  const label = host.querySelector(`[title="${path}"]`);
  const row = label?.closest('[role="button"]') as HTMLElement | null;
  if (!row) throw new Error(`No clickable row found for ${path}`);
  return row;
}

describe('open-file command contract', () => {
  it('intercepts workspace prose links while retaining browser behavior for external links', async () => {
    const onOpenFile = vi.fn();
    const host = mount(
      [
        {
          kind: 'message',
          id: 'message-1',
          role: 'assistant',
          text: '[workspace](src/prose.ts) and [external](https://example.com/docs)',
        },
      ],
      {
        classifyLink: (href) =>
          href === 'src/prose.ts' ? { kind: 'workspace-file', path: href } : { kind: 'external' },
        onOpenFile,
      }
    );
    await nextPaint();

    const workspaceLink = host.querySelector('a[href="src/prose.ts"]') as HTMLElement | null;
    const externalLink = host.querySelector(
      'a[href="https://example.com/docs"]'
    ) as HTMLElement | null;
    expect(workspaceLink).not.toBeNull();
    expect(externalLink).not.toBeNull();

    expect(dispatchLinkClick(workspaceLink!)).toBe(true);
    expect(onOpenFile).toHaveBeenCalledWith({
      path: 'src/prose.ts',
      itemId: 'message-1#0',
      source: 'prose-link',
    });

    expect(dispatchLinkClick(externalLink!)).toBe(false);
    expect(onOpenFile).toHaveBeenCalledTimes(1);
  });

  it('routes diff, file-operation, and resource file rows through onOpenFile', async () => {
    const onOpenFile = vi.fn();
    const host = mount(
      [
        {
          kind: 'diff',
          id: 'edit-1:src/diff.ts',
          path: 'src/diff.ts',
          oldText: 'before',
          newText: 'after',
          status: 'done',
        },
        {
          kind: 'file-op',
          id: 'file-op-1',
          op: 'read',
          status: 'done',
          ops: [{ path: 'src/file-op.ts' }],
        },
        {
          kind: 'resource-link',
          id: 'resource-1',
          uri: 'src/resource.ts',
          name: 'resource.ts',
          target: { kind: 'workspace-file', path: 'src/resource.ts' },
          status: 'done',
        },
      ],
      { onOpenFile }
    );
    await nextPaint();

    clickableRowForPath(host, 'src/diff.ts').click();
    clickableRowForPath(host, 'src/file-op.ts').click();
    const resourceRow = Array.from(host.querySelectorAll<HTMLElement>('[role="button"]')).find(
      (element) => element.textContent?.includes('src/resource.ts')
    );
    expect(resourceRow).toBeDefined();
    resourceRow!.click();

    expect(onOpenFile.mock.calls.map(([arg]) => arg)).toEqual([
      { path: 'src/diff.ts', itemId: 'edit-1:src/diff.ts', source: 'diff' },
      { path: 'src/file-op.ts', itemId: 'file-op-1', source: 'file-op' },
      { path: 'src/resource.ts', itemId: 'resource-1', source: 'resource-link' },
    ]);
  });

  it('routes file mentions through onClickMention', async () => {
    const onClickMention = vi.fn();
    const mentionProvider: MentionProvider = {
      resolve: (token) => ({ id: token, label: token, name: 'mention.ts', kind: 'file' }),
    };
    const host = mount(
      [{ kind: 'message', id: 'message-1', role: 'assistant', text: 'Open @src/mention.ts' }],
      { onClickMention },
      mentionProvider
    );
    await nextPaint();

    const mention = Array.from(host.querySelectorAll<HTMLElement>('span')).find(
      (element) => element.textContent === 'mention.ts' && element.style.cursor === 'pointer'
    );
    expect(mention).toBeDefined();
    mention!.click();

    expect(onClickMention).toHaveBeenCalledWith({
      id: 'src/mention.ts',
      label: 'mention.ts',
      kind: 'file',
      itemId: 'message-1#0',
      source: 'prose-mention',
    });
  });
});
