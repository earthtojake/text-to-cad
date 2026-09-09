/**
 * Spacing block stories — demonstrates paragraph and block gap rules.
 *
 * A single `\n` within a paragraph produces a tight line break (not a new
 * paragraph), while `\n\n` produces a paragraph with a smaller PROSE_GAP, and
 * non-prose blocks (code fence) keep the larger BLOCK_GAP on both sides.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost } from '@/stories/_harness/chat-host';

const meta: Meta = {
  title: 'Rows/Markdown/Spacing',
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
          text: [
            'First line of a paragraph.',
            'Second line — same paragraph, soft break (single \\n).',
            'Third line — still the same paragraph.',
            '',
            'This is a new paragraph after a blank line (`\\n\\n`).',
            'It should have a small gap above, not a big block gap.',
            '',
            'Another paragraph here.',
            '',
            '```ts',
            'const x = 1; // code block follows with a larger gap',
            '```',
            '',
            'Back to prose after the code fence — larger gap above.',
          ].join('\n'),
        },
      ]}
      height={460}
    />
  ),
};
