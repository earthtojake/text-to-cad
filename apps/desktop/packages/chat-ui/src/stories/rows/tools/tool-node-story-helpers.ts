import type { TranscriptApi } from '@state/transcript';
import type { ToolNode, ToolStatus, TranscriptTurn } from '@/model';
import type { ScriptStep } from '@/stories/_harness/chat-host';

export function toolNodeTurn(item: ToolNode): TranscriptTurn {
  return {
    id: 'tool-node-story-turn',
    seq: 0,
    initiator: 'agent',
    items: [{ ...item, seq: item.seq } as TranscriptTurn['items'][number]],
  };
}

export function setToolNode(item: ToolNode): ScriptStep {
  return {
    kind: 'call',
    fn: (api: TranscriptApi) => {
      const current = api.activeTurn.get();
      api.activeTurn.set(
        {
          id: current?.id ?? 'tool-node-story-active-turn',
          seq: current?.seq ?? 0,
          initiator: 'agent',
          items: [{ ...item, seq: item.seq } as TranscriptTurn['items'][number]],
        },
        'generating'
      );
    },
  };
}

export function streamToolNode(
  base: ToolNode,
  updates: Array<{
    afterMs: number;
    status?: ToolStatus;
    inputSummary?: string;
    agentId?: string;
    children?: ToolNode[];
  }>
): ScriptStep[] {
  const steps: ScriptStep[] = [setToolNode(base)];
  let current = base;
  for (const update of updates) {
    steps.push({ kind: 'wait', ms: update.afterMs });
    current = {
      ...current,
      ...(update.status !== undefined ? { status: update.status } : {}),
      ...(update.inputSummary !== undefined && 'toolCallId' in current
        ? { inputSummary: update.inputSummary }
        : {}),
      ...(update.agentId !== undefined && current.kind === 'spawn-subagent-tool-call'
        ? { agentId: update.agentId }
        : {}),
      ...(update.children !== undefined ? { children: update.children } : {}),
    } as ToolNode;
    steps.push(setToolNode(current));
  }
  steps.push({ kind: 'wait', ms: 300 });
  steps.push({ kind: 'call', fn: (api) => api.activeTurn.commit('done') });
  return steps;
}
