/**
 * Command-chip stories.
 *
 * Verifies that advertised /-commands in message text are rendered as styled
 * chips via the CommandProvider pipeline.  Unknown /tokens remain plain text.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { CommandProvider } from '@/index';
import { ChatHost } from '@/stories/_harness/chat-host';

const meta: Meta = {
  title: 'Rows/Markdown/CommandChip',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

/** Stub provider recognising a fixed set of advertised commands. */
const stubCommandProvider: CommandProvider = {
  resolve(token) {
    const advertised = ['web', 'search-files', 'explain'];
    if (!advertised.includes(token)) return null;
    return { name: token };
  },
};

export const KnownCommand: Story = {
  render: () => (
    <ChatHost
      commandProvider={stubCommandProvider}
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'user',
          text: 'Please run /web and find me the latest news.',
        },
        {
          kind: 'message',
          id: 'm2',
          role: 'assistant',
          text: 'Sure! I will use /web to search for the latest news. You can also use /search-files to look through local files or /explain to get an explanation.',
        },
      ]}
      height={220}
    />
  ),
};

export const UnknownCommand: Story = {
  render: () => (
    <ChatHost
      commandProvider={stubCommandProvider}
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'user',
          text: 'Run /foo and /web please.',
        },
        {
          kind: 'message',
          id: 'm2',
          role: 'assistant',
          text: '/foo is not a known command so it stays as plain text. /web is advertised so it becomes a chip.',
        },
      ]}
      height={200}
    />
  ),
};

export const NoProvider: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: 'Without a command provider /web and /search-files stay as plain text.',
        },
      ]}
      height={120}
    />
  ),
};
