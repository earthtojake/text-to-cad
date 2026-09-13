/**
 * Table block stories.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep, streamMessage } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Markdown/Table',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

export const Default: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: '| Name | Type | Default |\n|------|------|---------|\n| `fontSize` | `number` | `14` |\n| `lineHeight` | `number` | `22` |\n| `fontFamily` | `string` | `Inter` |',
        },
      ]}
      height={200}
    />
  ),
};

// 8 columns — exercises horizontal scroll when container is narrower than tableWidth.
export const Wide: Story = {
  name: 'Wide (8 columns)',
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: [
            '| Alpha | Beta | Gamma | Delta | Epsilon | Zeta | Eta | Theta |',
            '|-------|------|-------|-------|---------|------|-----|-------|',
            '| aaa-1 | bbb-1 | ccc-1 | ddd-1 | eee-1 | fff-1 | ggg-1 | hhh-1 |',
            '| aaa-2 | bbb-2 | ccc-2 | ddd-2 | eee-2 | fff-2 | ggg-2 | hhh-2 |',
            '| This cell has a very long value that should be truncated with an ellipsis | short | short | short | short | short | short | short |',
          ].join('\n'),
        },
      ]}
      height={200}
    />
  ),
};

// 20 rows — verifies formula height calculation for tall tables.
export const Tall: Story = {
  name: 'Tall (20 rows)',
  render: () => {
    const header = '| # | Item | Status | Notes |';
    const sep = '|---|------|--------|-------|';
    const rows = Array.from(
      { length: 20 },
      (_, i) =>
        `| ${i + 1} | Item ${i + 1} | ${i % 3 === 0 ? 'Done' : i % 3 === 1 ? 'In progress' : 'Pending'} | Some note for row ${i + 1} |`
    );
    return (
      <ChatHost
        items={[
          {
            kind: 'message',
            id: 'm1',
            role: 'assistant',
            text: [header, sep, ...rows].join('\n'),
          },
        ]}
        height={800}
      />
    );
  },
};

const TABLE_STREAMING_BODY = [
  'Comparison of authentication strategies:\n\n',
  '| Strategy | Stateless | Revocable | Complexity |\n',
  '|----------|-----------|-----------|------------|\n',
  '| JWT | Yes | No | Low |\n',
  '| Session | No | Yes | Low |\n',
  '| OAuth | Yes | Yes | High |\n',
].join('');

export const Generating: Story = {
  render: () => (
    <ScriptedChat
      height={280}
      script={scenario(
        [
          seedStep([
            {
              kind: 'message',
              id: 'u1',
              role: 'user',
              text: 'Compare authentication strategies',
            },
          ]),
        ],
        streamMessage({ id: 'a1', text: TABLE_STREAMING_BODY, chunkMs: 55 })
      )}
    />
  ),
};
