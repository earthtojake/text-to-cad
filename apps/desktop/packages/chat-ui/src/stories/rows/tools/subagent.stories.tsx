/**
 * Subagent tool-call stories — ACP spawn-subagent-tool-call rendered with the
 * dedicated two-line subagent row.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ToolNode, ToolStatus } from '@/model';
import { ChatHost, ChatHostExpanded, ScriptedChat } from '@/stories/_harness/chat-host';
import { type MatrixRow, ToolNodeStateMatrix } from '@/stories/_harness/state-matrix';
import { streamToolNode, toolNodeTurn } from './tool-node-story-helpers';

const meta: Meta = {
  title: 'Rows/Tools/Subagent',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

const SUBAGENT_ROWS: MatrixRow[] = [
  { label: 'Spawning', status: 'running' },
  { label: 'Running', status: 'running' },
  { label: 'Completed', status: 'done' },
  { label: 'Failed', status: 'error', error: 'Subagent exited before producing a summary' },
];

function rowId(label: string): string {
  return label.toLowerCase().replaceAll(' ', '-');
}

function executeNode(
  id: string,
  seq: number,
  command: string,
  status: ToolStatus = 'running'
): ToolNode {
  return {
    kind: 'execute-tool-call',
    id,
    seq,
    toolCallId: id,
    title: 'Execute',
    status,
    command,
    outputText: status === 'running' ? 'checking failing shards...' : 'all shards passed',
  };
}

function searchNode(id: string, seq: number, query: string, status: ToolStatus = 'done'): ToolNode {
  return {
    kind: 'search-tool-call',
    id,
    seq,
    toolCallId: id,
    title: 'Search',
    status,
    query,
    matchCount: status === 'running' ? undefined : 8,
  };
}

function subagentNode(
  status: ToolStatus,
  id = `subagent-${status}`,
  options: {
    background?: boolean;
    agentId?: string | null;
    children?: ToolNode[];
  } = {}
): ToolNode {
  const agentId =
    options.agentId === null
      ? undefined
      : (options.agentId ?? (status === 'running' ? undefined : `agent-${id}`));
  return {
    kind: 'spawn-subagent-tool-call',
    id,
    seq: 0,
    toolCallId: id,
    title: 'Subagent',
    status,
    name: 'Investigate failing check',
    background: options.background,
    ...(agentId ? { agentId } : {}),
    ...(options.children ? { children: options.children } : {}),
  };
}

function runningSubagentWithChildren(id: string): ToolNode {
  return subagentNode('running', id, {
    agentId: `agent-${id}`,
    children: [
      searchNode(`${id}-search`, 1, 'failing CI shard logs'),
      executeNode(`${id}-execute`, 2, 'pnpm test -- --runInBand'),
    ],
  });
}

function spawningSubagentWithChildren(id: string): ToolNode {
  return subagentNode('running', id, {
    agentId: null,
    children: [
      searchNode(`${id}-search`, 1, 'failing CI shard logs', 'running'),
      executeNode(`${id}-execute`, 2, 'pnpm test -- --runInBand'),
    ],
  });
}

function completedSubagentWithChildren(id: string): ToolNode {
  return subagentNode('done', id, {
    agentId: `agent-${id}`,
    children: [
      searchNode(`${id}-search`, 1, 'regression window'),
      executeNode(`${id}-execute`, 2, 'pnpm lint', 'done'),
    ],
  });
}

export const StateMatrix: Story = {
  render: () => (
    <ToolNodeStateMatrix
      rowHeight={96}
      rows={SUBAGENT_ROWS}
      build={(status, row) =>
        subagentNode(status, `subagent-${rowId(row.label)}`, {
          agentId: row.label === 'Spawning' ? null : `agent-${rowId(row.label)}`,
        })
      }
    />
  ),
};

export const RunningCollapsedNoPreview: Story = {
  render: () => (
    <ChatHost
      height={120}
      items={[toolNodeTurn(runningSubagentWithChildren('subagent-running-collapsed'))]}
    />
  ),
};

export const SpawningCollapsedShimmer: Story = {
  render: () => (
    <ChatHost
      height={120}
      items={[toolNodeTurn(spawningSubagentWithChildren('subagent-spawning-collapsed'))]}
    />
  ),
};

export const RunningExpanded: Story = {
  render: () => (
    <ChatHostExpanded
      height={220}
      expandId="subagent-running-expanded"
      items={[toolNodeTurn(runningSubagentWithChildren('subagent-running-expanded'))]}
    />
  ),
};

export const CompletedWithChildrenCollapsed: Story = {
  render: () => (
    <ChatHost
      height={120}
      items={[toolNodeTurn(completedSubagentWithChildren('subagent-completed-collapsed'))]}
    />
  ),
};

export const CompletedWithChildrenExpanded: Story = {
  render: () => (
    <ChatHostExpanded
      height={220}
      expandId="subagent-completed-expanded"
      items={[toolNodeTurn(completedSubagentWithChildren('subagent-completed-expanded'))]}
    />
  ),
};

export const Background: Story = {
  render: () => (
    <ChatHost
      height={96}
      items={[
        toolNodeTurn(
          subagentNode('running', 'subagent-bg', {
            background: true,
            agentId: 'agent-subagent-bg',
          })
        ),
      ]}
    />
  ),
};

export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={180}
      script={streamToolNode(subagentNode('running', 'subagent-stream', { agentId: null }), [
        { afterMs: 700, agentId: 'agent-subagent-stream' },
        {
          afterMs: 700,
          children: [
            searchNode('subagent-stream-search', 1, 'latest failing job output', 'running'),
          ],
        },
        {
          afterMs: 700,
          children: [
            searchNode('subagent-stream-search', 1, 'latest failing job output'),
            executeNode('subagent-stream-execute', 2, 'pnpm --filter @emdash/chat-ui test'),
          ],
        },
        { afterMs: 900, status: 'done' },
      ])}
    />
  ),
};
