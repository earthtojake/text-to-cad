/**
 * ToolGroup stories — hierarchical tool calls rendered as collapsible composite rows.
 *
 * Running collapsed groups show a child preview. Settled collapsed groups are
 * header-only until expanded. No visual inset between levels.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ToolNode, ToolStatus, TranscriptTurn } from '@/model';
import { ChatHost, ScriptedChat, type ScriptStep } from '@/stories/_harness/chat-host';
import { ToolNodeStateMatrix } from '@/stories/_harness/state-matrix';

const meta: Meta = {
  title: 'Rows/Tools/ToolGroup',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

function searchNode(id: string, seq: number, query: string, status: ToolStatus = 'done'): ToolNode {
  return {
    kind: 'search-tool-call',
    id,
    seq,
    toolCallId: id,
    title: 'Search',
    status,
    query,
  };
}

function executeNode(
  id: string,
  seq: number,
  command: string,
  status: ToolStatus = 'done'
): ToolNode {
  return {
    kind: 'execute-tool-call',
    id,
    seq,
    toolCallId: id,
    title: 'Execute',
    status,
    command,
  };
}

function modifyFileNode(
  id: string,
  seq: number,
  path: string,
  oldText: string,
  newText: string,
  status: ToolStatus = 'done'
): ToolNode {
  return {
    kind: 'modify-file-tool-call',
    id,
    seq,
    toolCallId: id,
    title: 'Edit',
    status,
    path,
    oldText,
    newText,
  };
}

function toolGroupNode(
  id: string,
  seq: number,
  label: string,
  children: ToolNode[],
  status: ToolStatus = 'done'
): ToolNode {
  return {
    kind: 'tool-group',
    id,
    seq,
    label,
    groupKind: 'read-batch',
    status,
    children,
  };
}

function turn(...items: TranscriptTurn['items']): TranscriptTurn {
  return {
    id: 'story-turn',
    seq: 0,
    initiator: 'user',
    items,
  };
}

function userMessage(id: string, text: string): TranscriptTurn['items'][number] {
  return { kind: 'message', id, seq: 0, role: 'user', text };
}

function refactorGroup(status: ToolStatus = 'done'): ToolNode {
  return toolGroupNode(
    'p1',
    1,
    'refactor',
    [
      searchNode('c1', 0, 'auth token references'),
      executeNode('c2', 1, 'npx tsc --noEmit'),
      modifyFileNode(
        'c3',
        2,
        'src/auth/token.ts',
        'function verify(tok) {',
        'export function verify(tok: string): boolean {'
      ),
    ],
    status
  );
}

function pipelineGroup(): ToolNode {
  return toolGroupNode('root', 1, 'pipeline', [
    toolGroupNode('sub', 0, 'compile', [
      executeNode('leaf1', 0, 'tsc'),
      modifyFileNode('leaf2', 1, 'dist/index.js', '', '"use strict";\nexports.main = main;'),
    ]),
    searchNode('leaf3', 1, 'lint warnings'),
  ]);
}

function streamingGroup(childCount: number, status: ToolStatus = 'running'): ToolNode {
  const children = [
    searchNode('c1', 0, 'TypeScript strict-mode errors'),
    executeNode('c2', 1, 'npx tsc --noEmit 2>&1 | head -20'),
    modifyFileNode(
      'c3',
      2,
      'src/auth/token.ts',
      'function verify(tok) {\n  return tok !== null;\n}',
      'export function verify(tok: string): boolean {\n  return tok.length > 0;\n}\n'
    ),
    searchNode('c4', 3, 'remaining lint warnings'),
  ];
  return toolGroupNode('p1', 1, 'analyse_and_fix', children.slice(0, childCount), status);
}

function setStreamingGroup(childCount: number, status?: ToolStatus): ScriptStep {
  return {
    kind: 'call',
    fn: (api) => {
      const current = api.activeTurn.get();
      api.activeTurn.set(
        {
          id: current?.id ?? 'story-active-turn',
          seq: current?.seq ?? 0,
          initiator: 'agent',
          items: [streamingGroup(childCount, status)] as TranscriptTurn['items'],
        },
        'generating'
      );
    },
  };
}

// ── Committed (static) stories ────────────────────────────────────────────────

export const StateMatrix: Story = {
  render: () => <ToolNodeStateMatrix rowHeight={220} build={(status) => refactorGroup(status)} />,
};

/**
 * A single-level hierarchy: one completed parent tool call with three children.
 * Settled groups start collapsed as a header-only summary. Click the header to expand.
 */
export const CommittedCollapsed: Story = {
  render: () => (
    <ChatHost
      height={300}
      items={[turn(userMessage('u1', 'Refactor the auth module'), refactorGroup())]}
    />
  ),
};

/**
 * Same hierarchy in the expanded state.
 * Seeded with the same items as CommittedCollapsed but the parent id is in the
 * initial `viewState` (collapsed = expanded due to inverted semantics).
 * Click the `refactor` header to expand.
 */
export const CommittedExpanded: Story = {
  render: () => (
    <ChatHost
      height={400}
      items={[turn(userMessage('u1', 'Refactor the auth module'), refactorGroup())]}
    />
  ),
};

/**
 * Multi-level nesting: a root parent has a child that is itself a parent.
 * No indentation between levels — only the CollapseHeader chrome signals hierarchy.
 */
export const MultiLevel: Story = {
  render: () => (
    <ChatHost
      height={400}
      items={[turn(userMessage('u1', 'Run the full pipeline'), pipelineGroup())]}
    />
  ),
};

// ── Streaming story ───────────────────────────────────────────────────────────

/**
 * Active streaming: a parent tool starts running, then children stream in one
 * by one. The preview window auto-scrolls to the newest child while the parent
 * is still active. A final commit settles the turn and shows the collapsed summary.
 *
 * Click the parent header to expand and see the full child stack.
 */
export const Streaming: Story = {
  render: () => (
    <ScriptedChat
      height={350}
      script={[
        {
          kind: 'seed',
          items: [turn(userMessage('u1', 'Analyse and fix the repository'))],
        },
        // Parent starts running, then children appear inside the same group.
        setStreamingGroup(0),
        { kind: 'wait', ms: 700 },
        setStreamingGroup(1),
        { kind: 'wait', ms: 900 },
        setStreamingGroup(2),
        { kind: 'wait', ms: 400 },
        setStreamingGroup(3),
        { kind: 'wait', ms: 600 },
        setStreamingGroup(4, 'done'),
        { kind: 'wait', ms: 300 },
        {
          kind: 'call',
          fn: (api) => api.activeTurn.commit('done'),
        },
      ]}
    />
  ),
};
