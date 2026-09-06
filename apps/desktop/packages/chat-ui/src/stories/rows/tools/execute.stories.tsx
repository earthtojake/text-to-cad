/**
 * Execute row stories — shell command execution in each status.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import { ChatHost, ScriptedChat } from '@/stories/_harness/chat-host';
import { ToolStateMatrix } from '@/stories/_harness/state-matrix';
import { scenario, seedStep, streamExecute } from '@/stories/_harness/streaming/scenario';

const meta: Meta = {
  title: 'Rows/Tools/Execute',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

export const StateMatrix: Story = {
  render: () => (
    <ToolStateMatrix
      build={(status) => ({
        kind: 'execute',
        id: `ex-matrix-${status}`,
        command: 'pnpm run build',
        status,
        startedAt: Date.now() - 3000,
        ...(status !== 'running' ? { durationMs: 3000 } : {}),
      })}
    />
  ),
};

export const Running: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex1',
          command: 'ls -a',
          status: 'running',
          startedAt: Date.now() - 3000,
        },
      ]}
      height={120}
    />
  ),
};

export const DescriptionHeader: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex-description',
          inputSummary: 'Installing Dependencies',
          command: 'pnpm install',
          status: 'running',
          startedAt: Date.now() - 1800,
        },
      ]}
      height={120}
    />
  ),
};

/** Streaming simulation: execute starts running then transitions to done. */
export const RunningStreamed: Story = {
  render: () => (
    <ScriptedChat
      height={160}
      script={scenario(
        [seedStep([{ kind: 'message', id: 'u1', role: 'user', text: 'Run the build' }])],
        streamExecute({ id: 'ex-stream', command: 'pnpm run build', durationMs: 1200 })
      )}
    />
  ),
};

export const Done: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex2',
          command: 'ls -a',
          status: 'done',
          startedAt: Date.now() - 5000,
          durationMs: 5000,
        },
      ]}
      height={120}
    />
  ),
};

/** Duration omitted — e.g. when replaying from a stored transcript with no durationMs. */
export const DoneNoDuration: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex3',
          command: 'ls -a',
          status: 'done',
          startedAt: 0,
        },
      ]}
      height={120}
    />
  ),
};

export const Error: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex4',
          command: 'pnpm run test',
          status: 'error',
          error: 'Test command failed with exit code 1',
          startedAt: Date.now() - 8000,
          durationMs: 8000,
        },
      ]}
      height={120}
    />
  ),
};

/** Long single-line command — demos horizontal scroll inside the body. */
export const LongCommand: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex5',
          command: 'find . -type f -name "*.ts" | xargs grep -l "import.*from.*solid-js"',
          status: 'done',
          startedAt: Date.now() - 2000,
          durationMs: 2000,
        },
      ]}
      height={120}
    />
  ),
};

/**
 * Multi-line command — exercises:
 *  - Collapsed cap (3 lines with fade overlay).
 *  - Click to expand (up to expandedMaxLines = 16, then scrollable).
 *  - Bash syntax highlighting across multiple statements.
 */
export const MultiLineCommand: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex-multi',
          command: [
            'git fetch origin',
            'git checkout -b feature/my-branch',
            'pnpm install',
            'pnpm run build --filter=@emdash/chat-ui',
            'pnpm run typecheck',
            'pnpm run lint',
            'pnpm run test',
            'echo "All checks passed"',
          ].join('\n'),
          status: 'done',
          startedAt: Date.now() - 12000,
          durationMs: 12000,
        },
      ]}
      height={300}
    />
  ),
};

/**
 * Many lines — exceeds expandedMaxLines (16). Expanding shows a scrollable area
 * capped at 16 lines; the card height stays deterministic.
 */
export const ManyLines: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex-many',
          command: Array.from(
            { length: 24 },
            (_, i) => `echo "Step ${i + 1}: processing item ${i + 1} of 24"`
          ).join('\n'),
          status: 'done',
          startedAt: Date.now() - 5000,
          durationMs: 5000,
        },
      ]}
      height={500}
    />
  ),
};

/** Permission request beneath a running execute row. */
export const RequestingPermission: Story = {
  render: () => (
    <ChatHost
      items={[
        {
          kind: 'execute',
          id: 'ex-perm',
          command: 'pnpm run build --filter=emdash-desktop',
          status: 'running',
          startedAt: Date.now() - 1200,
        },
      ]}
      height={160}
    />
  ),
};
