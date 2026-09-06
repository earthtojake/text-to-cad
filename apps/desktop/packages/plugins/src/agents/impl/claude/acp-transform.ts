import type { SessionUpdate } from '@agentclientprotocol/sdk';
import type { NormalizedEvent } from '@emdash/core/runtimes/acp/api';

/**
 * Claude-specific enrichment of a baseline `NormalizedEvent`.
 *
 * The Claude ACP adapter stamps subagent child updates with
 * `_meta.claudeCode.parentToolUseId` to indicate that a tool call was produced
 * by a nested agent (Task/Agent tool). This function promotes that value to the
 * first-class `parentToolCallId` field so downstream consumers never need to
 * know about `claudeCode`.
 *
 * Returns the original update object unchanged when:
 * - The update is not a `tool_call` or `tool_update`.
 * - The vendor field is absent or not a string.
 */
export function enrichClaudeUpdate(update: NormalizedEvent, raw: SessionUpdate): NormalizedEvent {
  if (update.kind === 'message' && update.role === 'user') {
    const text = update.text.trim();
    if (isLocalCommandChunk(text)) return { kind: 'ignored' };
    const notification = parseTaskNotification(text);
    if (notification) {
      return {
        kind: 'subagent_update',
        agentId: notification.taskId,
        toolCallId: notification.toolUseId,
        status: notification.status,
        summary: notification.summary,
        outputFile: notification.outputFile,
      };
    }
    return update;
  }

  if (update.kind !== 'tool_call' && update.kind !== 'tool_update') return update;

  const parentToolUseId = (
    raw._meta as { claudeCode?: { parentToolUseId?: unknown } } | null | undefined
  )?.claudeCode?.parentToolUseId;

  const parentPatch =
    typeof parentToolUseId === 'string' ? { parentToolCallId: parentToolUseId } : {};
  const outputPatch =
    update.outputText === undefined && rawOutputText(raw) !== undefined
      ? { outputText: rawOutputText(raw)! }
      : {};

  const toolName = claudeToolName(raw);
  const parentToolCallId = parentPatch.parentToolCallId ?? update.parentToolCallId;

  if (toolName === 'Agent' || toolName === 'Task') {
    const asyncLaunch = parseAsyncLaunch(raw);
    return {
      kind: 'subagent',
      toolCallId: update.toolCallId,
      title: asyncLaunch?.description ?? update.title ?? 'Agent',
      status: asyncLaunch ? 'in_progress' : update.status,
      parentToolCallId,
      inputSummary: agentInputSummary(raw),
      ...outputPatch,
      ...(asyncLaunch ? { background: true } : {}),
      ...(asyncLaunch?.agentId !== undefined ? { agentId: asyncLaunch.agentId } : {}),
      ...(asyncLaunch?.outputFile !== undefined ? { outputFile: asyncLaunch.outputFile } : {}),
    };
  }

  const input = rawToolInput(raw);
  if (toolName === 'WebSearch') {
    const query = stringField(input, 'query') ?? queryFromTitle(update.title);
    if (query) {
      return {
        kind: 'search',
        toolCallId: update.toolCallId,
        query,
        scope: 'web',
        status: update.status,
        parentToolCallId,
        ...outputPatch,
      };
    }
  }

  if (toolName === 'WebFetch') {
    const rawUrl = stringField(input, 'url') ?? urlFromTitle(update.title);
    if (rawUrl) {
      return {
        kind: 'web_fetch',
        toolCallId: update.toolCallId,
        url: sanitizeUrl(rawUrl),
        status: update.status,
        parentToolCallId,
        ...outputPatch,
      };
    }
  }

  const mcp = toolName ? parseMcpToolName(toolName) : null;
  if (mcp) {
    const inputSummary = summarizeInput(input);

    // Claude refinement updates often repeat the tool name without repeating
    // rawInput. Re-emitting a sparse `mcp_tool` event would replace the start
    // event's safe summary and map a missing status back to "running". Keep it
    // as a generic update so the transcript reducer merges only fields that
    // were actually present.
    if (update.kind === 'tool_update' && (inputSummary === undefined || update.status === null)) {
      return { ...update, ...parentPatch, ...outputPatch };
    }

    return {
      kind: 'mcp_tool',
      toolCallId: update.toolCallId,
      server: mcp.server,
      tool: mcp.tool,
      status: update.status,
      parentToolCallId,
      ...(inputSummary ? { inputSummary } : {}),
    };
  }

  if (toolName === 'ExitPlanMode') {
    // The plan itself is the call's text content; the row names what it is.
    return { ...update, ...parentPatch, ...outputPatch, title: 'Plan for approval' };
  }

  if (!parentPatch.parentToolCallId && outputPatch.outputText === undefined) return update;
  return { ...update, ...parentPatch, ...outputPatch };
}

type ClaudeMeta = {
  claudeCode?: {
    parentToolUseId?: unknown;
    toolName?: unknown;
    toolResponse?: unknown;
  };
};

type AsyncLaunch = {
  agentId: string;
  outputFile?: string;
  description?: string;
};

type TaskNotification = {
  taskId: string;
  toolUseId: string;
  outputFile?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  summary?: string;
};

function claudeMeta(raw: SessionUpdate): ClaudeMeta['claudeCode'] | undefined {
  return (raw._meta as ClaudeMeta | null | undefined)?.claudeCode;
}

function claudeToolName(raw: SessionUpdate): string | null {
  const toolName = claudeMeta(raw)?.toolName;
  return typeof toolName === 'string' ? toolName : null;
}

function agentInputSummary(raw: SessionUpdate): string | undefined {
  const input = rawToolInput(raw);
  return typeof input?.description === 'string' ? input.description : undefined;
}

function rawToolInput(raw: SessionUpdate): Record<string, unknown> | undefined {
  const input = (raw as unknown as { rawInput?: unknown }).rawInput;
  return input && typeof input === 'object' ? (input as Record<string, unknown>) : undefined;
}

function stringField(input: Record<string, unknown> | undefined, key: string): string | undefined {
  const value = input?.[key];
  return typeof value === 'string' && value.trim() ? value.trim() : undefined;
}

function queryFromTitle(title: string | null): string | undefined {
  if (!title) return undefined;
  const query = title.trim().replace(/^['"]|['"]$/g, '');
  return query && query.toLowerCase() !== 'web search' ? query : undefined;
}

function urlFromTitle(title: string | null): string | undefined {
  if (!title) return undefined;
  const url = title.replace(/^Fetch\s+/i, '').trim();
  return url && url.toLowerCase() !== 'fetch' ? url : undefined;
}

function parseMcpToolName(name: string): { server: string; tool: string } | null {
  const match = /^mcp__([\s\S]+?)__([\s\S]+)$/.exec(name);
  return match?.[1] && match[2] ? { server: match[1], tool: match[2] } : null;
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

function parseAsyncLaunch(raw: SessionUpdate): AsyncLaunch | null {
  const response = claudeMeta(raw)?.toolResponse as
    | {
        isAsync?: unknown;
        status?: unknown;
        agentId?: unknown;
        outputFile?: unknown;
        description?: unknown;
      }
    | null
    | undefined;
  if (
    response?.isAsync === true &&
    response.status === 'async_launched' &&
    typeof response.agentId === 'string'
  ) {
    return {
      agentId: response.agentId,
      ...(typeof response.outputFile === 'string' ? { outputFile: response.outputFile } : {}),
      ...(typeof response.description === 'string' ? { description: response.description } : {}),
    };
  }

  const text = rawText(raw);
  if (!text.includes('Async agent launched successfully.')) return null;
  const agentId = /^agentId:\s+([^\s]+)/m.exec(text)?.[1];
  if (!agentId) return null;
  const outputFile = /^output_file:\s+(.+)$/m.exec(text)?.[1]?.trim();
  return {
    agentId,
    ...(outputFile ? { outputFile } : {}),
  };
}

function rawText(raw: SessionUpdate): string {
  const parts: string[] = [];
  const content = (raw as { content?: unknown; rawOutput?: unknown }).content;
  collectText(content, parts);
  collectText((raw as { rawOutput?: unknown }).rawOutput, parts);
  return parts.join('\n');
}

function rawOutputText(raw: SessionUpdate): string | undefined {
  const rawOutput = (raw as { rawOutput?: unknown }).rawOutput;
  return typeof rawOutput === 'string' && rawOutput.length > 0 ? rawOutput : undefined;
}

function collectText(value: unknown, parts: string[]): void {
  if (typeof value === 'string') {
    parts.push(value);
    return;
  }
  if (!value || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    for (const item of value) collectText(item, parts);
    return;
  }
  const maybeText = (value as { text?: unknown }).text;
  if (typeof maybeText === 'string') parts.push(maybeText);
  collectText((value as { content?: unknown }).content, parts);
}

function isLocalCommandChunk(text: string): boolean {
  return text.startsWith('<local-command-') || text.includes('<command-name>');
}

export function parseTaskNotification(text: string): TaskNotification | null {
  if (!text.trimStart().startsWith('<task-notification>')) return null;
  const taskId = getTag(text, 'task-id');
  const toolUseId = getTag(text, 'tool-use-id');
  if (!taskId || !toolUseId) return null;
  return {
    taskId,
    toolUseId,
    status: toNotificationStatus(getTag(text, 'status')),
    ...(getTag(text, 'output-file') ? { outputFile: getTag(text, 'output-file')! } : {}),
    ...(getTag(text, 'summary') ? { summary: getTag(text, 'summary')! } : {}),
  };
}

function getTag(text: string, tag: string): string | null {
  const match = new RegExp(`<${tag}>([\\s\\S]*?)</${tag}>`).exec(text);
  return match?.[1]?.trim() ?? null;
}

function toNotificationStatus(
  status: string | null
): 'pending' | 'in_progress' | 'completed' | 'failed' {
  switch (status) {
    case 'completed':
      return 'completed';
    case 'failed':
      return 'failed';
    case 'pending':
      return 'pending';
    default:
      return 'in_progress';
  }
}
