import type { ChatItem, TranscriptTurn } from '@/model';

export type ActiveTurnEvent =
  | { type: 'message_chunk'; id: string; role?: 'user' | 'assistant' | 'thought'; text: string }
  | { type: 'thinking_chunk'; id: string; text: string; startedAt?: number }
  | { type: 'thinking_done'; id: string; durationMs?: number }
  | { type: 'tool_start'; id: string; name: string; inputSummary?: string; parentId?: string }
  | {
      type: 'tool_update';
      id: string;
      status?: 'running' | 'done' | 'error';
      name?: string;
      inputSummary?: string;
    }
  | {
      type: 'file_op_start';
      id: string;
      op: 'read' | 'edit' | 'delete' | 'move';
      ops: Array<{ path: string }>;
      parentId?: string;
    }
  | {
      type: 'file_op_update';
      id: string;
      ops?: Array<{ path: string }>;
      status?: 'running' | 'done' | 'error';
    }
  | { type: 'execute_start'; id: string; command: string; startedAt?: number; parentId?: string }
  | {
      type: 'execute_update';
      id: string;
      status?: 'running' | 'done' | 'error';
      durationMs?: number;
    }
  | {
      type: 'diff_start';
      id: string;
      path: string;
      oldText: string | null;
      newText: string;
      parentId?: string;
    }
  | { type: 'diff_update'; id: string; newText?: string; status?: 'running' | 'done' | 'error' }
  | {
      type: 'plan_update';
      id: string;
      entries: Array<{
        content: string;
        status: 'pending' | 'in_progress' | 'completed';
        priority: 'high' | 'medium' | 'low';
      }>;
      streaming?: boolean;
    }
  | { type: 'plan_removed'; id: string }
  | { type: 'resource_link_start'; id: string; [key: string]: unknown }
  | { type: 'resource_link_update'; id: string; [key: string]: unknown };

export function applyTurnEvent(
  turn: TranscriptTurn | null,
  event: ActiveTurnEvent
): TranscriptTurn {
  const current = turn?.items ?? [];
  const items = [...current] as ChatItem[];
  const idx = items.findIndex((item) => item.id === event.id);
  const existing = idx >= 0 ? items[idx] : null;
  const existingRecord = existing as Record<string, unknown> | null;
  const existingText = typeof existingRecord?.text === 'string' ? existingRecord.text : '';
  const existingStatus =
    existingRecord?.status === 'running' ||
    existingRecord?.status === 'done' ||
    existingRecord?.status === 'error'
      ? existingRecord.status
      : 'running';
  const baseTurn: TranscriptTurn =
    turn ??
    ({
      id: 'story-active-turn',
      seq: 0,
      initiator: event.type === 'message_chunk' && event.role === 'user' ? 'user' : 'agent',
      items: [],
    } satisfies TranscriptTurn);
  const upsert = (item: ChatItem): TranscriptTurn => {
    if (idx >= 0) items[idx] = { ...existing, ...item } as ChatItem;
    else items.push({ ...item, seq: items.length } as ChatItem);
    return { ...baseTurn, items: items as TranscriptTurn['items'] };
  };

  switch (event.type) {
    case 'message_chunk':
      return upsert({
        kind: 'message',
        id: event.id,
        role: event.role ?? 'assistant',
        text: `${existingText}${event.text}`,
        streaming: (event.role ?? 'assistant') === 'assistant',
      } as ChatItem);
    case 'thinking_chunk':
      return upsert({
        kind: 'thinking',
        id: event.id,
        segmentId: event.id,
        status: 'thinking',
        text: `${existingText}${event.text}`,
        startedAt:
          event.startedAt ??
          (typeof existingRecord?.startedAt === 'number' ? existingRecord.startedAt : Date.now()),
      } as ChatItem);
    case 'thinking_done':
      return upsert({
        kind: 'thinking',
        id: event.id,
        status: 'done',
        durationMs: event.durationMs,
      } as ChatItem);
    case 'tool_start':
      return upsert({
        kind: 'tool',
        id: event.id,
        name: event.name,
        status: 'running',
        inputSummary: event.inputSummary,
        parentId: event.parentId,
      } as ChatItem);
    case 'tool_update':
      return upsert({ ...event, kind: 'tool', id: event.id } as ChatItem);
    case 'file_op_start':
      return upsert({
        kind: 'file-op',
        id: event.id,
        op: event.op,
        status: 'running',
        ops: event.ops,
        parentId: event.parentId,
      } as ChatItem);
    case 'file_op_update':
      return upsert({
        kind: 'file-op',
        id: event.id,
        ops: event.ops ?? (Array.isArray(existingRecord?.ops) ? existingRecord.ops : []),
        status: event.status ?? existingStatus,
      } as ChatItem);
    case 'execute_start':
      return upsert({
        kind: 'execute',
        id: event.id,
        command: event.command,
        status: 'running',
        startedAt: event.startedAt ?? Date.now(),
        parentId: event.parentId,
      } as ChatItem);
    case 'execute_update':
      return upsert({
        kind: 'execute',
        id: event.id,
        status: event.status ?? existingStatus,
        durationMs: event.durationMs,
      } as ChatItem);
    case 'diff_start':
      return upsert({
        kind: 'diff',
        id: event.id,
        path: event.path,
        oldText: event.oldText,
        newText: event.newText,
        status: 'running',
        parentId: event.parentId,
      } as ChatItem);
    case 'diff_update':
      return upsert({
        kind: 'diff',
        id: event.id,
        newText:
          event.newText ??
          (typeof existingRecord?.newText === 'string' ? existingRecord.newText : ''),
        status: event.status ?? existingStatus,
      } as ChatItem);
    case 'plan_update':
      return upsert({
        kind: 'plan',
        id: event.id,
        entries: event.entries,
        streaming: event.streaming,
      } as ChatItem);
    case 'plan_removed':
      return {
        ...baseTurn,
        items: items.filter((item) => item.id !== event.id) as TranscriptTurn['items'],
      };
    case 'resource_link_start':
    case 'resource_link_update':
      return upsert({ kind: 'resource-link', ...event } as unknown as ChatItem);
  }
}

export function finalizeTurn(turn: TranscriptTurn): TranscriptTurn {
  const items = turn.items as ChatItem[];
  return {
    ...turn,
    items: items.map((item) => {
      if (item.kind === 'message' && 'streaming' in item) return { ...item, streaming: false };
      if ('status' in item && item.status === 'running') return { ...item, status: 'done' };
      if (item.kind === 'plan') return { ...item, streaming: false };
      return item;
    }) as TranscriptTurn['items'],
  };
}
