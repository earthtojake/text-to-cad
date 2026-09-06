import type { ToolNode, TranscriptTurn } from '@emdash/chat-ui';
import { estimateThinkingTokens } from '@emdash/core/runtimes/acp/api/client';

export interface CadTurnSummary {
  id: string;
  userText: string;
  assistantText: string;
  activities: CadActivity[];
  artifacts: CadArtifact[];
  durationMs?: number;
  thinkingTokens: number;
  state: 'working' | 'completed' | 'stopped' | 'error';
}

const MIN_DURABLE_WORK_DURATION_MS = 1_000;

export interface CadActivity {
  id: string;
  title: string;
  detail?: string;
  status: 'running' | 'done' | 'error';
}

export interface CadArtifact {
  path: string;
  operation: 'created' | 'updated' | 'deleted' | 'model';
}

const CAD_HIDDEN_CONTEXT_MARKER = "You are working from Hardcore's integrated CAD workspace.";

export function summarizeCadTurns(
  turns: readonly TranscriptTurn[],
  activeTurnId: string | null,
  modelPath: string,
  persistedDurationsMs: Readonly<Record<string, number>> = {}
): CadTurnSummary[] {
  return turns.flatMap((turn) => {
    const userText: string[] = [];
    const assistantText: string[] = [];
    const thinkingText: string[] = [];
    const activities: CadActivity[] = [];
    const artifacts = new Map<string, CadArtifact>();

    for (const item of turn.items) {
      if (item.kind === 'message') {
        const text = item.role === 'user' ? visibleCadPrompt(item.text) : item.text.trim();
        if (!text) continue;
        if (item.role === 'user') userText.push(text);
        else assistantText.push(text);
        continue;
      }
      if (item.kind === 'thinking') {
        if (item.text.trim()) thinkingText.push(item.text);
        continue;
      }
      if (item.kind === 'resource-link') continue;
      collectToolNode(item, activities, artifacts);
    }

    const state = turnState(turn, activeTurnId);
    const persistedDurationMs = persistedDurationsMs[turn.id];
    const durationMs =
      (persistedDurationMs !== undefined && persistedDurationMs >= MIN_DURABLE_WORK_DURATION_MS
        ? persistedDurationMs
        : undefined) ??
      (turn.timingSource !== 'replay' && isReliableLiveTiming(turn.startedAt)
        ? turn.durationMs
        : undefined);
    if (state === 'completed' && activities.length > 0 && modelPath) {
      artifacts.set(modelPath, { path: modelPath, operation: 'model' });
    }

    if (
      userText.length === 0 &&
      assistantText.length === 0 &&
      activities.length === 0 &&
      artifacts.size === 0
    ) {
      return [];
    }

    return [
      {
        id: turn.id,
        userText: userText.join('\n\n'),
        assistantText: assistantText.join('\n\n'),
        activities,
        artifacts: [...artifacts.values()],
        ...(durationMs !== undefined ? { durationMs } : {}),
        thinkingTokens: estimateThinkingTokens(thinkingText.join('\n')),
        state,
      },
    ];
  });
}

function isReliableLiveTiming(startedAt: number | undefined): boolean {
  // Provider replay without timestamps uses synthetic 0, 1, 2… event times.
  // Epoch milliseconds distinguish a real live measurement from that fallback.
  return startedAt !== undefined && startedAt >= 1_000_000_000_000;
}

export function formatWorkedDuration(durationMs?: number): string {
  if (durationMs === undefined) return 'Work details';

  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000));
  if (totalSeconds < 1) return 'Worked for <1s';

  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) return `Worked for ${hours}h ${minutes}m ${seconds}s`;
  if (minutes > 0) return `Worked for ${minutes}m ${seconds}s`;
  return `Worked for ${seconds}s`;
}

export function visibleCadPrompt(text: string): string {
  const markerIndex = text.indexOf(CAD_HIDDEN_CONTEXT_MARKER);
  return text.slice(0, markerIndex === -1 ? undefined : markerIndex).trim();
}

export function cadOutputPath(path: string): string {
  if (/\.(?:step|stp)\.py$/i.test(path)) return path.slice(0, -3);
  return path.toLowerCase().endsWith('.py') ? `${path.slice(0, -3)}.step` : path;
}

function collectToolNode(
  node: ToolNode,
  activities: CadActivity[],
  artifacts: Map<string, CadArtifact>
): void {
  if (node.kind === 'tool-group') {
    for (const child of node.children) collectToolNode(child, activities, artifacts);
    return;
  }

  activities.push({
    id: node.id,
    title: node.title || activityTitle(node),
    detail: activityDetail(node),
    status: node.status,
  });

  if (node.kind === 'create-file-tool-call') {
    artifacts.set(node.path, { path: node.path, operation: 'created' });
  } else if (node.kind === 'modify-file-tool-call') {
    artifacts.set(node.path, { path: node.path, operation: 'updated' });
  } else if (node.kind === 'delete-file-tool-call') {
    artifacts.set(node.path, { path: node.path, operation: 'deleted' });
  }

  for (const child of node.children ?? []) collectToolNode(child, activities, artifacts);
}

function activityTitle(node: Exclude<ToolNode, { kind: 'tool-group' }>): string {
  switch (node.kind) {
    case 'execute-tool-call':
      return 'Run CAD command';
    case 'read-tool-call':
      return 'Inspect file';
    case 'create-file-tool-call':
      return 'Create file';
    case 'modify-file-tool-call':
      return 'Update file';
    case 'delete-file-tool-call':
      return 'Delete file';
    case 'search-tool-call':
      return 'Search project';
    case 'mcp-tool-call':
      return node.tool;
    case 'web-fetch-tool-call':
      return 'Open reference';
    case 'spawn-subagent-tool-call':
      return `Run ${node.name}`;
    case 'create-plan-tool-call':
      return 'Plan design work';
    case 'unknown-tool-call':
      return node.name;
  }
}

function activityDetail(node: Exclude<ToolNode, { kind: 'tool-group' }>): string | undefined {
  if (node.inputSummary) return node.inputSummary;
  switch (node.kind) {
    case 'execute-tool-call':
      return node.command;
    case 'read-tool-call':
      return node.path ?? node.resource;
    case 'create-file-tool-call':
    case 'modify-file-tool-call':
    case 'delete-file-tool-call':
      return node.path;
    case 'search-tool-call':
      return node.query;
    case 'mcp-tool-call':
      return node.server ? `${node.server} · ${node.tool}` : node.tool;
    case 'web-fetch-tool-call':
      return node.pageTitle ?? node.url;
    default:
      return undefined;
  }
}

function turnState(turn: TranscriptTurn, activeTurnId: string | null): CadTurnSummary['state'] {
  if (turn.id === activeTurnId) return 'working';
  if (turn.outcome?.kind === 'error' || turn.outcome?.kind === 'interrupted') return 'error';
  if (turn.outcome?.kind === 'cancelled') return 'stopped';
  return 'completed';
}
