import { estimateThinkingTokens, type TranscriptTurn } from '@emdash/core/runtimes/acp/api/client';

export type AgentProgress = {
  phase: string;
  thinkingTokens: number;
};

export function deriveAgentProgress(
  turn: TranscriptTurn | null | undefined,
  hasPendingPermission: boolean
): AgentProgress {
  const items = turn?.items ?? [];
  const reasoning = items
    .filter((item) => item.kind === 'thinking')
    .map((item) => item.text)
    .join('\n');
  const thinkingTokens = estimateThinkingTokens(reasoning);

  if (hasPendingPermission) return { phase: 'Waiting for approval', thinkingTokens };

  const activeThinking = items.some(
    (item) => item.kind === 'thinking' && item.status === 'thinking'
  );
  if (activeThinking) return { phase: 'Thinking', thinkingTokens };

  const latest = items.at(-1);
  if (!latest) return { phase: 'Starting', thinkingTokens };
  if (latest.kind === 'message' && latest.role === 'assistant') {
    return { phase: 'Writing response', thinkingTokens };
  }
  if ('status' in latest && latest.status === 'running') {
    return { phase: toolPhase(latest), thinkingTokens };
  }
  return { phase: 'Working', thinkingTokens };
}

function toolPhase(item: TranscriptTurn['items'][number]): string {
  const kind = item.kind;
  if (
    kind === 'create-file-tool-call' ||
    kind === 'modify-file-tool-call' ||
    kind === 'delete-file-tool-call'
  ) {
    return 'Updating model files';
  }
  if (isImageGeneration(item)) return 'Generating image';
  if (
    kind === 'search-tool-call' &&
    (item.scope === 'web' || /^web\s+search\b/i.test(item.title))
  ) {
    return 'Searching the web';
  }
  if (kind === 'web-fetch-tool-call') return 'Opening web page';
  if (kind === 'read-tool-call' || kind === 'search-tool-call') return 'Reviewing model context';
  if (kind === 'create-plan-tool-call') return 'Planning';
  return 'Running CAD tools';
}

function isImageGeneration(item: TranscriptTurn['items'][number]): boolean {
  if (item.kind === 'unknown-tool-call') {
    return item.name.toLowerCase() === 'image generation' || item.toolKind === 'image-generation';
  }
  if (item.kind !== 'mcp-tool-call') return false;
  return `${item.server ?? ''} ${item.tool}`.toLowerCase().includes('image_gen');
}
