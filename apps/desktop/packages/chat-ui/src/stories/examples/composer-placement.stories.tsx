import { onCleanup, onMount } from 'solid-js';
import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import {
  DEFAULT_THEME,
  createChatContext,
  createChatState,
  createChatView,
  pinTopMode,
  type ChatView,
} from '@/index';

const meta: Meta = {
  title: 'Examples/ComposerPlacement',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

function ComposerPlacementDemo() {
  let hostEl: HTMLDivElement | undefined;
  let view: ChatView | null = null;
  let heroEl: HTMLDivElement | null = null;
  let composerEl: HTMLFormElement | null = null;
  let sent = false;

  const context = createChatContext({ theme: DEFAULT_THEME });
  const state = createChatState(context);

  const toggleMessage = () => {
    if (!view || !composerEl) return;
    const button = composerEl.querySelector('button');
    if (sent) {
      sent = false;
      state.transcript.history.seed([]);
      view.setComposerPlacement('center', { animate: true });
      if (button) button.textContent = 'Send';
      return;
    }

    sent = true;
    state.transcript.history.seed([
      {
        id: 'placement-turn',
        seq: 0,
        initiator: 'user',
        items: [
          {
            kind: 'message',
            id: 'u-placement',
            seq: 0,
            role: 'user',
            text: 'Build a dashboard for monitoring parallel agent runs.',
          },
        ],
      },
    ]);
    view.setScrollMode(pinTopMode('u-placement'));
    view.setComposerPlacement('bottom', { animate: true });
    if (button) button.textContent = 'Reset';
  };

  onMount(() => {
    if (!hostEl) return;

    view = createChatView({
      context,
      state,
      parent: hostEl,
      composer: 'slot',
      composerPlacement: 'center',
      stickToBottom: true,
      pinUserMessages: true,
      onViewMounted(v) {
        if (v.heroSlot) {
          heroEl = document.createElement('div');
          heroEl.style.textAlign = 'center';
          heroEl.style.fontSize = '28px';
          heroEl.style.fontWeight = '650';
          heroEl.style.letterSpacing = '-0.03em';
          heroEl.textContent = 'What are we building today?';
          v.heroSlot.append(heroEl);
        }

        if (v.composerSlot) {
          composerEl = document.createElement('form');
          composerEl.style.display = 'flex';
          composerEl.style.gap = '8px';
          composerEl.style.alignItems = 'center';
          composerEl.style.padding = '12px';
          composerEl.style.border = '1px solid color-mix(in srgb, currentColor 12%, transparent)';
          composerEl.style.borderRadius = '16px';
          composerEl.style.background = 'color-mix(in srgb, Canvas 88%, transparent)';
          composerEl.style.boxShadow =
            '0 16px 48px color-mix(in srgb, currentColor 12%, transparent)';
          composerEl.innerHTML = `
            <input
              aria-label="Message"
              value="Build a dashboard for monitoring parallel agent runs."
              style="flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; font: inherit;"
            />
            <button
              type="submit"
              style="border: 0; border-radius: 999px; padding: 8px 14px; background: currentColor; color: Canvas;"
            >Send</button>
          `;
          composerEl.addEventListener('submit', (event) => {
            event.preventDefault();
            toggleMessage();
          });
          v.composerSlot.append(composerEl);
          composerEl.querySelector('input')?.focus();
        }
      },
    });
  });

  onCleanup(() => {
    heroEl?.remove();
    composerEl?.remove();
    view?.dispose();
    state.dispose();
    context.dispose();
  });

  return (
    <div
      ref={(el) => {
        hostEl = el;
      }}
      style={{
        width: '880px',
        height: '560px',
        border: '1px solid color-mix(in srgb, currentColor 10%, transparent)',
        'border-radius': '16px',
        overflow: 'hidden',
      }}
    />
  );
}

export const EmptyToConversation: Story = {
  render: () => <ComposerPlacementDemo />,
};
