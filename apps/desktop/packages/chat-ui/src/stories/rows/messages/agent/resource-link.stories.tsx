/**
 * ResourceLink row stories — single-line resource/file references.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost } from '@/stories/_harness/chat-host';

const meta: Meta = {
  title: 'Rows/Messages/Agent/ResourceLink',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

/** TypeScript file in the workspace — uses devicon for the file type. */
export const WorkspaceFile: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'resource-link',
          id: 'rl1',
          name: 'model.ts',
          title: 'model.ts',
          uri: 'packages/chat-ui/src/model.ts',
          target: { kind: 'workspace-file', path: 'packages/chat-ui/src/model.ts' },
        },
      ]}
      height={80}
    />
  ),
};

/** External URL — opens in a new tab. */
export const ExternalUrl: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'resource-link',
          id: 'rl2',
          name: 'solidjs-docs',
          title: 'SolidJS Docs',
          uri: 'https://docs.solidjs.com',
          target: { kind: 'external', url: 'https://docs.solidjs.com' },
        },
      ]}
      height={80}
    />
  ),
};

/** Opaque URI — no target action; shows the URI for copy. */
export const OpaqueUri: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'resource-link',
          id: 'rl3',
          name: 'context-snapshot',
          title: 'Agent context snapshot',
          uri: 'acp://context/abc123',
          target: { kind: 'opaque' },
        },
      ]}
      height={80}
    />
  ),
};

/** Resource link that ended with an error — shows the circle-X icon after the path. */
export const Error: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'resource-link',
          id: 'rl-err',
          name: 'model.ts',
          title: 'model.ts',
          uri: 'packages/chat-ui/src/model.ts',
          target: { kind: 'workspace-file', path: 'packages/chat-ui/src/model.ts' },
          status: 'error',
        },
      ]}
      height={80}
    />
  ),
};

/** Multiple resource links in a sequence. */
export const Multiple: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'resource-link',
          id: 'rl4',
          name: 'transcript.ts',
          uri: 'packages/chat-ui/src/state/transcript.ts',
          target: { kind: 'workspace-file', path: 'packages/chat-ui/src/state/transcript.ts' },
        },
        {
          kind: 'resource-link',
          id: 'rl5',
          name: 'model.ts',
          uri: 'packages/chat-ui/src/model.ts',
          target: { kind: 'workspace-file', path: 'packages/chat-ui/src/model.ts' },
        },
        {
          kind: 'resource-link',
          id: 'rl6',
          name: 'ChatRoot.tsx',
          uri: 'packages/chat-ui/src/ChatRoot.tsx',
          target: { kind: 'workspace-file', path: 'packages/chat-ui/src/ChatRoot.tsx' },
        },
      ]}
      height={160}
    />
  ),
};
