/**
 * CodeBlock block stories.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep, streamMessage } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Markdown/CodeBlock',
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
          text: '```typescript\nfunction greet(name: string): string {\n  return `Hello, ${name}!`;\n}\n\nconsole.log(greet("World"));\n```',
        },
      ]}
      height={200}
    />
  ),
};

export const Bash: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: '```bash\n# Install dependencies\nnpm install\n\n# Run development server\nnpm run dev\n```',
        },
      ]}
      height={180}
    />
  ),
};

const CODE_STREAMING_BODY = [
  'Here is the implementation:\n\n',
  '```typescript\n',
  'function greet(name: string): string {\n',
  '  return `Hello, ${name}!`;\n',
  '}\n',
  '\n',
  'console.log(greet("World"));\n',
  '```\n\n',
  'Call `greet` with any name string.',
].join('');

/**
 * A single very long line that exceeds the column width — verifies that the
 * code block clips and scrolls horizontally without overflowing the message
 * column, and that the copy button stays pinned at the top-right.
 */
export const LongLines: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm1',
          role: 'assistant',
          text: '```typescript\nconst result = await fetchSomeData({ endpoint: "https://api.example.com/v1/this/is/a/very/long/path/that/keeps/going", headers: { Authorization: `Bearer ${token}`, "X-Request-Id": requestId, "Content-Type": "application/json" }, params: { include: "everything", expand: "deeply", format: "verbose" } });\nconst short = 1;\nconst alsoShort = true;\n```',
        },
      ]}
      height={200}
    />
  ),
};

export const Generating: Story = {
  render: () => (
    <ScriptedChat
      height={260}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Show me a greet function' }])],
        streamMessage({ id: 'a1', text: CODE_STREAMING_BODY, chunkMs: 55 })
      )}
    />
  ),
};

/**
 * FenceCloseHighlight — verifies that the code block is highlighted at the
 * exact moment its closing fence arrives, with NO trailing blank line before
 * the next sentence starts. The highlight tokens should appear while "Now call
 * it with..." is still streaming, demonstrating fence-close commit timing.
 */
const FENCE_CLOSE_BODY = [
  'Here is a simple add function:\n\n',
  '```typescript\n',
  'function add(a: number, b: number): number {\n',
  '  return a + b;\n',
  '}\n',
  // Closing fence with no blank line — the code block should commit here.
  '```\n',
  'Now call it with `add(2, 3)` to get `5`. ',
  'You can also use it inside a reduce to sum an array of numbers.',
].join('');

export const FenceCloseHighlight: Story = {
  render: () => (
    <ScriptedChat
      height={340}
      script={scenario(
        [
          seedStep([
            { kind: 'message', id: 'u1', role: 'user', text: 'How do I add two numbers?' },
          ]),
        ],
        streamMessage({ id: 'a1', text: FENCE_CLOSE_BODY, chunkMs: 90 })
      )}
    />
  ),
};

/**
 * IncrementalHighlight — a code block followed by more streaming prose with a
 * blank line between them. The highlight should appear before the trailing
 * paragraph finishes, demonstrating the general settled-prefix commit.
 */
const INCREMENTAL_HIGHLIGHT_BODY = [
  'Here is a function you can use:\n\n',
  '```typescript\n',
  'function add(a: number, b: number): number {\n',
  '  return a + b;\n',
  '}\n',
  '```\n\n',
  'That covers the basic implementation. ',
  'You can extend it to handle edge cases like NaN or Infinity ',
  'by adding input validation at the top of the function body.',
].join('');

export const IncrementalHighlight: Story = {
  render: () => (
    <ScriptedChat
      height={360}
      script={scenario(
        [
          seedStep([
            { kind: 'message', id: 'u1', role: 'user', text: 'How do I add two numbers?' },
          ]),
        ],
        streamMessage({ id: 'a1', text: INCREMENTAL_HIGHLIGHT_BODY, chunkMs: 80 })
      )}
    />
  ),
};
