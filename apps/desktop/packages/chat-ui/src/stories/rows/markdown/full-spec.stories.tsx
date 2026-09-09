/**
 * FullSpec — a single assistant message that exercises every markdown feature
 * supported by chat-ui: headings, emphasis, inline code, links, @-mentions,
 * inline math, lists, task lists, blockquotes, fenced code, tables, and rules.
 *
 * Also validates the trailing-dot fix: "@src/auth/jwt.ts." in the sentence
 * below captures only `src/auth/jwt.ts`, not `src/auth/jwt.ts.`.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ChatMentionMeta, MentionProvider } from '@/index';
import { ChatHost } from '@/stories/_harness/chat-host';

const meta: Meta = {
  title: 'Rows/Markdown/FullSpec',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

// ── Demo MentionProvider ──────────────────────────────────────────────────────

const KNOWN_MENTIONS: Record<string, ChatMentionMeta> = {
  'src/auth/jwt.ts': {
    id: 'src/auth/jwt.ts',
    label: 'src/auth/jwt.ts',
    name: 'jwt.ts',
    kind: 'file',
    iconClass: 'devicon-typescript-plain colored',
  },
  'issue-42': {
    id: 'issue-42',
    label: 'issue-42',
    name: '#42',
    kind: 'issue',
  },
  'handleSubmit()': {
    id: 'handleSubmit()',
    label: 'handleSubmit()',
    name: 'handleSubmit()',
    kind: 'symbol',
  },
};

const demoMentionProvider: MentionProvider = {
  resolve: (token) => KNOWN_MENTIONS[token] ?? null,
};

// ── Full-spec markdown string ─────────────────────────────────────────────────

const SPEC = [
  '# Heading 1',
  '',
  '## Heading 2',
  '',
  '### Heading 3',
  '',
  'A paragraph with **bold**, *italic*, ***bold-italic***, ~~strikethrough~~, and `inline code` text.',
  '',
  'An [external link](https://example.com) and a [workspace link](src/auth/jwt.ts).',
  '',
  'Mentions inline in a sentence: open @src/auth/jwt.ts, track @issue-42, and call @handleSubmit().',
  'Sentence-final mention to test trailing-dot fix: see @src/auth/jwt.ts.',
  '',
  'Inline math: area $A = \\pi r^2$, golden ratio $\\varphi = \\frac{1+\\sqrt{5}}{2}$, and sum $\\sum_{i=1}^{n} i = \\frac{n(n+1)}{2}$ on one line.',
  '',
  '## Lists',
  '',
  '- Unordered item one',
  '  - Nested item a',
  '  - Nested item b',
  '- Unordered item two',
  '',
  '1. Ordered item one',
  '   1. Nested ordered a',
  '   2. Nested ordered b',
  '2. Ordered item two',
  '',
  '- [x] Completed task',
  '- [ ] Pending task',
  '- [x] Another done task',
  '',
  '## Blockquotes',
  '',
  '> This is a blockquote.',
  '> It spans multiple lines.',
  '>',
  '> > Nested blockquote goes here.',
  '',
  '## Code Block',
  '',
  '```typescript',
  'interface User {',
  '  id: string;',
  '  name: string;',
  '}',
  '',
  'function greet(user: User): string {',
  '  return `Hello, ${user.name}!`;',
  '}',
  '```',
  '',
  '## Table',
  '',
  '| Name | Type | Default | Description |',
  '|------|------|---------|-------------|',
  '| `fontSize` | `number` | `14` | Base font size in px |',
  '| `lineHeight` | `number` | `22` | Line height in px |',
  '| `fontFamily` | `string` | `Inter` | Font family name |',
  '| `monospace` | `string` | `JetBrains Mono` | Monospace font |',
  '',
  '---',
  '',
  'Paragraph after the horizontal rule.',
].join('\n');

// ── Story ─────────────────────────────────────────────────────────────────────

export const Default: Story = {
  render: () => (
    <ChatHost
      mentionProvider={demoMentionProvider}
      items={[{ kind: 'message', id: 'm1', role: 'assistant', text: SPEC }]}
      height={760}
    />
  ),
};
