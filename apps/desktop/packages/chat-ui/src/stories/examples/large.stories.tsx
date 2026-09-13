/**
 * Large transcript stories — large item counts for rendering validation.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { generateMockTranscript } from '@/mock-transcript';
import { ChatHost } from '@/stories/_harness/chat-host';

const meta: Meta = {
  title: 'Examples/Large',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

export const TenK: Story = {
  name: '10k items',
  render: () => <ChatHost items={generateMockTranscript(10000)} height={700} />,
};

export const TwoK: Story = {
  name: '2k items',
  render: () => <ChatHost items={generateMockTranscript(2000)} height={700} />,
};
