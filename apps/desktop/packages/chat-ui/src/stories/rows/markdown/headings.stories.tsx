/**
 * Headings block stories.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { scenario, seedStep, streamMessage } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Markdown/Headings',
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
          text: '# Heading 1\n\n## Heading 2\n\n### Heading 3\n\nBody text follows headings.',
        },
      ]}
      height={200}
    />
  ),
};

const HEADINGS_STREAMING = [
  '# Heading 1\n\n',
  '## Heading 2\n\n',
  '### Heading 3\n\n',
  'Body text follows headings.',
].join('');

export const Generating: Story = {
  render: () => (
    <ScriptedChat
      height={200}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Show me heading examples' }])],
        streamMessage({ id: 'a1', text: HEADINGS_STREAMING, chunkMs: 60 })
      )}
    />
  ),
};

// ── Regression: long mixed-style h2 heading that previously overlapped ─────────
//
// The heading ## **PHASE 1: CRITICAL CONCURRENCY FIXES** (Week 1 - 13 hours)
// was measured at body font size (14px) but rendered at h2 size (17px).  At
// narrow widths this causes the heading to wrap to more lines than reserved,
// pushing the bottom border into the next row.  Verify that the row height
// matches the rendered h2 at three container widths.

const LONG_HEADING_TEXT = [
  '## **PHASE 1: CRITICAL CONCURRENCY FIXES** (Week 1 - 13 hours)',
  '',
  '## **PHASE 2: PERFORMANCE IMPROVEMENTS** (Week 2 - 10 hours)',
  '',
  'Body text follows the long headings above.',
].join('\n\n');

export const LongMixedBoldHeading: Story = {
  name: 'Long mixed-bold h2 (narrow — regression)',
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm2',
          role: 'assistant',
          text: LONG_HEADING_TEXT,
        },
      ]}
      height={300}
      width={350}
    />
  ),
};

export const LongMixedBoldHeadingWide: Story = {
  name: 'Long mixed-bold h2 (wide)',
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'message',
          id: 'm3',
          role: 'assistant',
          text: LONG_HEADING_TEXT,
        },
      ]}
      height={300}
      width={700}
    />
  ),
};

export const LongMixedBoldHeadingStreaming: Story = {
  name: 'Long mixed-bold h2 (streaming)',
  render: () => (
    <ScriptedChat
      height={300}
      width={350}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u2', role: 'user', text: 'Give me a project plan' }])],
        streamMessage({ id: 'a2', text: LONG_HEADING_TEXT, chunkMs: 40 })
      )}
    />
  ),
};
