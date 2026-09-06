/**
 * Plan tool-call stories — ACP create-plan-tool-call rendered through the plan row.
 */

import type { Meta, StoryObj } from 'storybook-solidjs-vite';
import type { ChatPlanEntry, PlanState, ToolNode, ToolStatus } from '@/model';
import { ChatHost } from '@/stories/_harness/chat-host';
import { ToolNodeStateMatrix, type MatrixRow } from '@/stories/_harness/state-matrix';

const meta: Meta = {
  title: 'Rows/Tools/PlanToolCall',
  component: ChatHost,
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj<typeof ChatHost>;

const IN_PROGRESS_ENTRIES: ChatPlanEntry[] = [
  { content: 'Inspect the renderer registry', status: 'completed', priority: 'high' },
  { content: 'Add missing Storybook coverage', status: 'in_progress', priority: 'high' },
  { content: 'Run focused verification', status: 'pending', priority: 'medium' },
];

const DONE_ENTRIES: ChatPlanEntry[] = IN_PROGRESS_ENTRIES.map((entry) => ({
  ...entry,
  status: 'completed',
}));

function planToolNode(status: ToolStatus, id = `plan-tool-${status}`): ToolNode {
  return {
    kind: 'create-plan-tool-call',
    id,
    seq: 0,
    toolCallId: id,
    title: 'Create plan',
    status,
    planId: 'session-plan',
  };
}

function planForRow(row: MatrixRow): PlanState {
  const entries =
    row.label === 'Done' || row.label === 'Error' ? DONE_ENTRIES : IN_PROGRESS_ENTRIES;
  return {
    id: 'session-plan',
    updatedAt: Date.now(),
    entries: entries.map((entry, index) => ({ ...entry, id: `plan-entry-${row.label}-${index}` })),
  };
}

export const StateMatrix: Story = {
  render: () => (
    <ToolNodeStateMatrix
      rowHeight={140}
      build={(status) => planToolNode(status)}
      plan={planForRow}
    />
  ),
};
