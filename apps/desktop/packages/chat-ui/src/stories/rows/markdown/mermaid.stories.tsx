/**
 * Mermaid diagram block stories.
 *
 * Shows the 21:9 preview, idle SVG upgrade, click-to-view logging,
 * invalid-syntax fallback, and streaming fence completion.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep, streamMessage } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Markdown/Mermaid',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

const FLOWCHART = `\`\`\`mermaid
flowchart LR
  A[Start] --> B{Decision}
  B -->|Yes| C[Action A]
  B -->|No| D[Action B]
  C --> E[End]
  D --> E
\`\`\``;

export const Default: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: `Here is the architecture:\n\n${FLOWCHART}`,
        },
      ]}
      height={280}
    />
  ),
};

export const Standalone: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: FLOWCHART,
        },
      ]}
      height={220}
    />
  ),
};

export const MultipleBlocks: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: [
            'First diagram:',
            '',
            '```mermaid',
            'flowchart LR',
            '  A --> B --> C',
            '```',
            '',
            'Second diagram:',
            '',
            '```mermaid',
            'flowchart TD',
            '  Root --> Child1',
            '  Root --> Child2',
            '  Child1 --> Leaf',
            '```',
          ].join('\n'),
        },
      ]}
      height={500}
    />
  ),
};

export const InvalidSyntax: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: '```mermaid\nthis is not valid mermaid syntax @@@ ###\n```',
        },
      ]}
      height={220}
    />
  ),
};

export const MmdAlias: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: '```mmd\nflowchart LR\n  X --> Y\n```',
        },
      ]}
      height={220}
    />
  ),
};

const STREAMING_BODY = [
  'Let me diagram the flow:\n\n',
  '```mermaid\n',
  'flowchart LR\n',
  '  Parse[Parse input] --> Validate\n',
  '  Validate --> Process\n',
  '  Process --> Output\n',
  '```\n\n',
  'That covers the main path.',
].join('');

export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={300}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Show me the pipeline' }])],
        streamMessage({ id: 'a1', text: STREAMING_BODY, chunkMs: 60 })
      )}
    />
  ),
};
