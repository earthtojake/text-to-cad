import type { SessionUpdate } from '@agentclientprotocol/sdk';
import type { NormalizedEvent } from '@emdash/core/runtimes/acp/api';

type CodexToolInput = {
  server?: unknown;
  tool?: unknown;
  arguments?: unknown;
};

/** Provider names of Codex's multi-agent tools, as they arrive in `title`. */
const COLLAB_TOOLS = new Set(['spawnAgent', 'sendInput', 'wait', 'closeAgent']);

/** Promote Codex adapter metadata into provider-neutral transcript events. */
export function enrichCodexUpdate(update: NormalizedEvent, raw: SessionUpdate): NormalizedEvent {
  if (update.kind !== 'tool_call' && update.kind !== 'tool_update') return update;

  const activity = codexSubAgentActivity(update, raw);
  if (activity) return activity;

  const collab = codexCollabEvent(update, raw);
  if (collab) return collab;

  update = withFormattedOutput(update, raw);
  update = withMcpProgress(update, raw);

  if (
    update.kind === 'tool_call' &&
    update.toolKind === 'other' &&
    update.title.trim().toLowerCase() === 'image generation'
  ) {
    return { ...update, toolKind: 'image-generation' };
  }

  const input = codexToolInput(raw);
  if (!isMcpToolCall(raw, input)) return update;
  if (typeof input?.server !== 'string' || typeof input.tool !== 'string') return update;
  const inputSummary = summarizeInput(input.arguments);

  // Completion updates can omit arguments. Preserve the safe summary from the
  // start event by letting the normal tool-update reducer merge this update.
  if (update.kind === 'tool_update' && (inputSummary === undefined || update.status === null)) {
    return update;
  }

  return {
    kind: 'mcp_tool',
    toolCallId: update.toolCallId,
    server: input.server,
    tool: input.tool,
    status: update.status,
    parentToolCallId: update.parentToolCallId,
    ...(inputSummary ? { inputSummary } : {}),
  };
}

/**
 * Codex reports a command's result as `rawOutput.formatted_output`, not as
 * ACP text content. Promote it so the transcript keeps the output after the
 * live terminal is gone.
 */
function withFormattedOutput(
  update: Extract<NormalizedEvent, { kind: 'tool_call' | 'tool_update' }>,
  raw: SessionUpdate
): Extract<NormalizedEvent, { kind: 'tool_call' | 'tool_update' }> {
  if (update.outputText !== undefined) return update;
  const rawOutput = (raw as { rawOutput?: unknown }).rawOutput;
  const formatted =
    rawOutput && typeof rawOutput === 'object'
      ? (rawOutput as { formatted_output?: unknown }).formatted_output
      : undefined;
  if (typeof formatted !== 'string' || formatted.length === 0) return update;
  return { ...update, outputText: formatted };
}

/**
 * Codex streams MCP tool progress as `_meta.mcp_output_delta` on updates that
 * carry nothing else. Keep the latest line so the row can say what the
 * integration is doing while it runs.
 */
function withMcpProgress(
  update: Extract<NormalizedEvent, { kind: 'tool_call' | 'tool_update' }>,
  raw: SessionUpdate
): Extract<NormalizedEvent, { kind: 'tool_call' | 'tool_update' }> {
  if (update.kind !== 'tool_update') return update;
  const meta = raw._meta as { mcp_output_delta?: { data?: unknown } } | null | undefined;
  const data = meta?.mcp_output_delta?.data;
  if (typeof data !== 'string') return update;
  const line = data
    .split(/\r?\n/)
    .map((candidate) => candidate.trim())
    .filter(Boolean)
    .at(-1);
  if (!line) return update;
  return { ...update, progress: compactText(line, 160) };
}

type CollabInput = {
  prompt?: unknown;
  senderThreadId?: unknown;
  receiverThreadIds?: unknown;
  agentsStates?: unknown;
};

/** Current Codex reports child lifecycle separately from collaboration tool calls. */
function codexSubAgentActivity(
  update: Extract<NormalizedEvent, { kind: 'tool_call' | 'tool_update' }>,
  raw: SessionUpdate
): NormalizedEvent | null {
  const input = (raw as { rawInput?: unknown }).rawInput;
  if (!input || typeof input !== 'object') return null;
  const activity = input as Record<string, unknown>;
  if (
    activity.type !== 'subAgentActivity' ||
    typeof activity.agentThreadId !== 'string' ||
    !activity.agentThreadId ||
    typeof activity.agentPath !== 'string'
  ) {
    return null;
  }
  const agentId = activity.agentThreadId;
  switch (activity.kind) {
    case 'started':
      return {
        kind: 'subagent',
        toolCallId: update.toolCallId,
        title: compactText(
          activity.agentPath.split('/').filter(Boolean).at(-1) || 'Codex agent',
          100
        ),
        status: 'in_progress',
        parentToolCallId: update.parentToolCallId,
        background: true,
        agentId,
      };
    case 'completed':
    case 'interrupted':
      // This signal says the child stopped, not that its task failed. Codex
      // also emits interrupted when closing an already completed child.
      return { kind: 'subagent_update', agentId, status: 'completed' };
    case 'interacted':
      return describeCollabCall(update, 'Message to agent', activity.agentPath);
    default:
      return null;
  }
}

/**
 * Codex's multi-agent tools (spawnAgent / sendInput / wait / closeAgent)
 * arrive as opaque `other` tool calls. Surface the spawned agent as a
 * subagent row with its brief, describe the waits and messages, and close the
 * row when the agent is closed. The child thread itself never streams to us.
 */
function codexCollabEvent(
  update: Extract<NormalizedEvent, { kind: 'tool_call' | 'tool_update' }>,
  raw: SessionUpdate
): NormalizedEvent | null {
  const rawTitle = (raw as { title?: unknown }).title;
  const name = typeof rawTitle === 'string' ? rawTitle : update.title;
  if (!name || !COLLAB_TOOLS.has(name)) return null;
  const input = (raw as { rawInput?: unknown }).rawInput;
  if (!input || typeof input !== 'object') return null;
  const collab = input as CollabInput;
  if (typeof collab.senderThreadId !== 'string' && !Array.isArray(collab.receiverThreadIds)) {
    return null;
  }
  const receivers = Array.isArray(collab.receiverThreadIds)
    ? collab.receiverThreadIds.filter((id): id is string => typeof id === 'string')
    : [];
  const states =
    collab.agentsStates && typeof collab.agentsStates === 'object'
      ? (collab.agentsStates as Record<string, { status?: unknown }>)
      : {};
  const agentId = receivers[0] ?? Object.keys(states)[0];
  const prompt = typeof collab.prompt === 'string' ? compactText(collab.prompt, 200) : undefined;

  switch (name) {
    case 'spawnAgent':
      return {
        kind: 'subagent',
        toolCallId: update.toolCallId,
        title: 'Codex agent',
        // The spawn call completing means the agent is now running; only a
        // failed spawn ends the row here.
        status: update.status === 'failed' ? 'failed' : 'in_progress',
        parentToolCallId: update.parentToolCallId,
        ...(prompt ? { inputSummary: prompt } : {}),
        background: true,
        ...(agentId ? { agentId } : {}),
      };
    case 'closeAgent':
      if (update.kind === 'tool_update' && update.status === 'completed' && agentId) {
        // Closing ends the agent whatever it last reported, unless it failed.
        const reported = collabAgentStatus(states[agentId]?.status);
        return {
          kind: 'subagent_update',
          agentId,
          status: reported === 'failed' ? 'failed' : 'completed',
        };
      }
      return describeCollabCall(update, 'Close agent', agentId);
    case 'sendInput':
      return describeCollabCall(update, 'Message to agent', prompt ?? agentId);
    case 'wait':
      return describeCollabCall(update, 'Wait for agent', agentId);
    default:
      return null;
  }
}

function describeCollabCall(
  update: Extract<NormalizedEvent, { kind: 'tool_call' | 'tool_update' }>,
  title: string,
  inputSummary: string | undefined
): NormalizedEvent {
  const summary = inputSummary ? { inputSummary: shortAgentId(inputSummary) } : {};
  return update.kind === 'tool_call'
    ? { ...update, title, toolKind: 'other', ...summary }
    : { ...update, title, ...summary };
}

/** Thread ids are UUIDs; keep a message brief readable and an id short. */
function shortAgentId(value: string): string {
  return /^[0-9a-f-]{32,}$/i.test(value) ? `agent ${value.slice(0, 8)}` : value;
}

function collabAgentStatus(
  value: unknown
): Extract<NormalizedEvent, { kind: 'subagent_update' }>['status'] | undefined {
  if (typeof value !== 'string') return undefined;
  switch (value.toLowerCase()) {
    case 'completed':
    case 'done':
    case 'closed':
      return 'completed';
    case 'failed':
    case 'error':
    case 'errored':
      return 'failed';
    case 'running':
    case 'pendinginit':
      return 'in_progress';
    default:
      return undefined;
  }
}

function codexToolInput(raw: SessionUpdate): CodexToolInput | null {
  const value = (raw as unknown as { rawInput?: unknown }).rawInput;
  return value && typeof value === 'object' ? (value as CodexToolInput) : null;
}

function isMcpToolCall(raw: SessionUpdate, input: CodexToolInput | null): boolean {
  const meta = raw._meta as { is_mcp_tool_call?: unknown } | null | undefined;
  if (meta?.is_mcp_tool_call === true) return true;

  // Codex completion updates do not repeat the metadata marker, but do repeat
  // the structured MCP input. Requiring both names avoids reclassifying a
  // generic dynamic tool that happens to accept one similarly named field.
  return typeof input?.server === 'string' && typeof input.tool === 'string';
}

function summarizeInput(value: unknown): string | undefined {
  const candidates: Array<{ label: string; value: string }> = [];
  const seen = new WeakSet<object>();

  const visit = (current: unknown, depth: number): void => {
    if (!current || typeof current !== 'object' || depth > 4 || candidates.length >= 3) return;
    if (seen.has(current)) return;
    seen.add(current);

    if (Array.isArray(current)) {
      for (const item of current.slice(0, 5)) visit(item, depth + 1);
      return;
    }

    for (const [key, nested] of Object.entries(current)) {
      if (candidates.length >= 3) break;
      if (isSecretLikeKey(key)) continue;

      const label = safeSummaryLabel(key);
      if (label && typeof nested === 'string' && nested.trim()) {
        const text = label === 'URL' ? sanitizeUrl(nested.trim()) : compactText(nested);
        if (text && !candidates.some((candidate) => candidate.value === text)) {
          candidates.push({ label, value: text });
        }
        continue;
      }

      visit(nested, depth + 1);
    }
  };

  visit(value, 0);
  if (candidates.length === 0) return undefined;
  if (candidates.length === 1) return candidates[0]!.value;
  return compactText(candidates.map(({ label, value }) => `${label}: ${value}`).join(' · '), 200);
}

function safeSummaryLabel(key: string): string | null {
  const normalized = normalizeKey(key);
  if (normalized === 'query' || normalized.endsWith('_query')) return 'Query';
  if (
    normalized === 'url' ||
    normalized === 'uri' ||
    normalized.endsWith('_url') ||
    normalized.endsWith('_uri')
  ) {
    return 'URL';
  }
  if (normalized === 'path' || normalized.endsWith('_path')) return 'Path';
  if (
    normalized === 'file' ||
    normalized === 'filename' ||
    normalized.endsWith('_file') ||
    normalized.endsWith('_filename')
  ) {
    return 'File';
  }
  if (normalized === 'title') return 'Title';
  if (normalized === 'name') return 'Name';
  return null;
}

function isSecretLikeKey(key: string): boolean {
  const normalized = normalizeKey(key);
  const parts = normalized.split('_');
  return (
    parts.some((part) =>
      ['token', 'secret', 'password', 'passwd', 'credential', 'credentials', 'cookie'].includes(
        part
      )
    ) ||
    [
      'authorization',
      'auth',
      'private_key',
      'api_key',
      'access_key',
      'session',
      'session_id',
    ].includes(normalized) ||
    normalized.endsWith('_signature') ||
    normalized === 'sig'
  );
}

function normalizeKey(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
    .replace(/[^a-zA-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .toLowerCase();
}

function compactText(value: string, maxLength = 120): string {
  const text = value.replace(/\s+/g, ' ').trim();
  return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
}

function sanitizeUrl(value: string): string {
  if (/^data:/i.test(value)) return '[embedded data]';

  try {
    const url = new URL(value);
    let changed = false;
    if (url.username || url.password) {
      url.username = '';
      url.password = '';
      changed = true;
    }
    for (const key of [...url.searchParams.keys()]) {
      if (!isSecretLikeKey(key)) continue;
      url.searchParams.set(key, 'redacted');
      changed = true;
    }
    if (url.hash && isSecretLikeKey(url.hash.slice(1).split('=', 1)[0] ?? '')) {
      url.hash = 'redacted';
      changed = true;
    }
    return compactText(changed ? url.toString() : value);
  } catch {
    const withoutCredentials = value.replace(/(\/\/)[^/@\s]+@/, '$1');
    const redacted = withoutCredentials.replace(
      /([?&#])([^=&#]+)=([^&#]*)/g,
      (match, separator: string, key: string) =>
        isSecretLikeKey(key) ? `${separator}${key}=redacted` : match
    );
    return compactText(redacted);
  }
}
