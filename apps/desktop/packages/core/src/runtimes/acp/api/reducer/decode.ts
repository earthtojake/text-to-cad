/**
 * Baseline ACP SessionUpdate decoder.
 *
 * Converts raw ACP SDK SessionUpdate notifications into the parser's internal
 * NormalizedEvent vocabulary. This is the parser-owned equivalent of the
 * legacy toAgentUpdate in agent-update.ts — it is stateless, pure, and
 * handles all ACP-specific decoding:
 *
 *   - Extracts text from content blocks for message and thinking variants.
 *   - Extracts diff blocks from ToolCallContent arrays.
 *   - Passes status and kind through unchanged (no UI-level remapping here).
 *   - Preserves missing message ids for the stateful reducer to segment.
 *   - Sets parentToolCallId to null (providers enrich via EnrichHook).
 *   - Returns { kind: 'ignored' } for variants not yet rendered.
 */

import type { ContentBlock, SessionUpdate, ToolCallContent } from '@agentclientprotocol/sdk';
import type {
  NormalizedDiff,
  NormalizedEvent,
  NormalizedResourceLink,
  NormalizedToolLocation,
  NormalizedToolStatus,
  SessionUsage,
} from './normalized-event';

function extractDiffs(
  content: ReadonlyArray<ToolCallContent> | null | undefined
): NormalizedDiff[] {
  if (!content) return [];
  const diffs: NormalizedDiff[] = [];
  for (const block of content) {
    if (block.type === 'diff') {
      diffs.push({ path: block.path, oldText: block.oldText ?? null, newText: block.newText });
    }
  }
  return diffs;
}

function collectTextPayload(value: unknown, parts: string[]): void {
  if (!value || typeof value !== 'object') return;
  if (Array.isArray(value)) {
    for (const item of value) collectTextPayload(item, parts);
    return;
  }

  const raw = value as { type?: unknown; text?: unknown; content?: unknown };
  if (raw.type === 'text' && typeof raw.text === 'string') {
    parts.push(raw.text);
    return;
  }
  collectTextPayload(raw.content, parts);
}

function stripSingleCodeFence(text: string): string {
  const trimmed = text.trim();
  const match = /^```[^\n]*\n([\s\S]*?)\n```$/.exec(trimmed);
  return match ? match[1] : text;
}

function extractTextOutput(
  content: ReadonlyArray<ToolCallContent> | null | undefined
): string | undefined {
  if (!content) return undefined;
  const parts: string[] = [];
  for (const block of content) {
    const raw = block as { type?: unknown; content?: unknown; text?: unknown };
    if (raw.type === 'content') {
      const link = raw.content as { type?: unknown; name?: unknown; uri?: unknown } | null;
      if (link?.type === 'resource_link' && typeof link.uri === 'string') {
        // A linked resource inside a tool result (Codex's View Image) reads as a line.
        parts.push(
          typeof link.name === 'string' && link.name ? `${link.name}: ${link.uri}` : link.uri
        );
      } else {
        collectTextPayload(raw.content, parts);
      }
    } else if (raw.type === 'text' && typeof raw.text === 'string') {
      parts.push(raw.text);
    }
  }
  const text = parts.join('\n');
  return text ? stripSingleCodeFence(text) : undefined;
}

function extractTerminalId(update: SessionUpdate): string | undefined {
  const raw = update as unknown as {
    terminalId?: unknown;
    terminal_id?: unknown;
    content?: unknown;
  };
  if (typeof raw.terminalId === 'string') return raw.terminalId;
  if (typeof raw.terminal_id === 'string') return raw.terminal_id;
  // ACP attaches a terminal to a tool call as a content block
  // ({ type: 'terminal', terminalId }); Codex sends exactly that.
  if (Array.isArray(raw.content)) {
    for (const block of raw.content) {
      const candidate = block as { type?: unknown; terminalId?: unknown } | null;
      if (candidate?.type === 'terminal' && typeof candidate.terminalId === 'string') {
        return candidate.terminalId;
      }
    }
  }
  return undefined;
}

function extractInputSummary(update: SessionUpdate): string | undefined {
  const raw = update as unknown as {
    inputSummary?: unknown;
    input_summary?: unknown;
    description?: unknown;
  };
  if (typeof raw.inputSummary === 'string') return raw.inputSummary;
  if (typeof raw.input_summary === 'string') return raw.input_summary;
  if (typeof raw.description === 'string') return raw.description;
  return undefined;
}

/** Embedded text resources are kept whole up to this size; larger ones are cut. */
const EMBEDDED_RESOURCE_TEXT_LIMIT = 16_000;

type MessageContent =
  | { kind: 'text'; text: string }
  | { kind: 'link'; link: NormalizedResourceLink }
  | { kind: 'image' }
  | { kind: 'ignored' };

/**
 * Every content block a message chunk can carry. Text streams as-is,
 * resource links become rows, embedded text resources are inlined under their
 * uri, and images are attached by the runtime's attachment ingress (the chunk
 * itself keeps an empty text so the attachment has a message to hang on).
 * Audio and binary resources have no rendering and are skipped.
 */
function messageContent(content: ContentBlock): MessageContent {
  switch (content.type) {
    case 'text':
      return content.text ? { kind: 'text', text: content.text } : { kind: 'ignored' };
    case 'resource_link':
      return {
        kind: 'link',
        link: {
          uri: content.uri,
          name: content.name,
          ...(typeof content.title === 'string' ? { title: content.title } : {}),
          ...(typeof content.description === 'string' ? { description: content.description } : {}),
          ...(typeof content.mimeType === 'string' ? { mimeType: content.mimeType } : {}),
          ...(typeof content.size === 'number' ? { size: content.size } : {}),
        },
      };
    case 'resource': {
      const resource = content.resource as { uri?: unknown; text?: unknown };
      if (typeof resource.text !== 'string' || !resource.text) return { kind: 'ignored' };
      const body =
        resource.text.length > EMBEDDED_RESOURCE_TEXT_LIMIT
          ? `${resource.text.slice(0, EMBEDDED_RESOURCE_TEXT_LIMIT)}\n… (truncated)`
          : resource.text;
      const label = typeof resource.uri === 'string' && resource.uri ? `${resource.uri}\n` : '';
      return { kind: 'text', text: `\n${label}${body}\n` };
    }
    case 'image':
      return { kind: 'image' };
    default:
      return { kind: 'ignored' };
  }
}

function decodeMessageChunk(
  role: 'user' | 'assistant',
  update: Extract<SessionUpdate, { sessionUpdate: 'user_message_chunk' | 'agent_message_chunk' }>
): NormalizedEvent {
  const content = messageContent(update.content);
  if (content.kind === 'ignored') return { kind: 'ignored' };
  const base = { kind: 'message' as const, role, messageId: update.messageId ?? null };
  switch (content.kind) {
    case 'text':
      return { ...base, text: content.text };
    case 'link':
      return { ...base, text: '', links: [content.link] };
    case 'image':
      return { ...base, text: '' };
  }
}

function extractLocations(update: SessionUpdate): NormalizedToolLocation[] | undefined {
  const raw = (update as unknown as { locations?: unknown }).locations;
  if (!Array.isArray(raw)) return undefined;
  const locations: NormalizedToolLocation[] = [];
  for (const entry of raw) {
    const candidate = entry as { path?: unknown; line?: unknown } | null;
    if (typeof candidate?.path !== 'string' || !candidate.path) continue;
    locations.push({
      path: candidate.path,
      ...(typeof candidate.line === 'number' ? { line: candidate.line } : {}),
    });
  }
  return locations.length > 0 ? locations : undefined;
}

/** Claude reports account rate limits beside usage; the composer warns from them. */
function decodeRateLimit(value: unknown): SessionUsage['rateLimit'] | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const raw = value as {
    status?: unknown;
    resetsAt?: unknown;
    rateLimitType?: unknown;
    utilization?: unknown;
  };
  if (raw.status !== 'allowed' && raw.status !== 'allowed_warning' && raw.status !== 'rejected') {
    return undefined;
  }
  return {
    status: raw.status,
    ...(typeof raw.resetsAt === 'number' ? { resetsAt: raw.resetsAt } : {}),
    ...(typeof raw.rateLimitType === 'string' ? { rateLimitType: raw.rateLimitType } : {}),
    ...(typeof raw.utilization === 'number' ? { utilization: raw.utilization } : {}),
  };
}

function planEntries(raw: unknown): Extract<NormalizedEvent, { kind: 'plan' }>['entries'] {
  if (!Array.isArray(raw)) return [];
  return raw.map((entry) => {
    const candidate = entry as { content?: unknown; status?: unknown; priority?: unknown };
    return {
      content: typeof candidate.content === 'string' ? candidate.content : '',
      status: planEntryStatus(candidate.status),
      priority: planEntryPriority(candidate.priority),
    };
  });
}

function planEntryStatus(value: unknown): 'pending' | 'in_progress' | 'completed' {
  return value === 'in_progress' || value === 'completed' ? value : 'pending';
}

function planEntryPriority(value: unknown): 'high' | 'medium' | 'low' {
  return value === 'high' || value === 'low' ? value : 'medium';
}

/**
 * Decode a raw ACP SessionUpdate into a NormalizedEvent.
 * Stateless — does not depend on turn or session context.
 */
export function decodeSessionUpdate(update: SessionUpdate): NormalizedEvent {
  switch (update.sessionUpdate) {
    case 'user_message_chunk':
      return decodeMessageChunk('user', update);

    case 'agent_message_chunk':
      return decodeMessageChunk('assistant', update);

    case 'agent_thought_chunk': {
      if (update.content.type !== 'text' || !update.content.text) return { kind: 'ignored' };
      return {
        kind: 'thinking',
        messageId: update.messageId ?? null,
        text: update.content.text,
      };
    }

    case 'tool_call': {
      const terminalId = extractTerminalId(update);
      const inputSummary = extractInputSummary(update);
      const locations = extractLocations(update);
      // A call can carry text from the start (a plan awaiting approval, an
      // agent's brief, a startup failure); it is kept like a result.
      const outputText = extractTextOutput(update.content);
      return {
        kind: 'tool_call',
        toolCallId: update.toolCallId,
        title: update.title,
        toolKind: update.kind ?? null,
        status: (update.status as NormalizedToolStatus | undefined) ?? null,
        parentToolCallId: null,
        diffs: extractDiffs(update.content),
        ...(inputSummary !== undefined ? { inputSummary } : {}),
        ...(outputText !== undefined ? { outputText } : {}),
        ...(terminalId !== undefined ? { terminalId } : {}),
        ...(locations !== undefined ? { locations } : {}),
      };
    }

    case 'tool_call_update': {
      const outputText = extractTextOutput(update.content ?? undefined);
      const terminalId = extractTerminalId(update);
      const locations = extractLocations(update);
      return {
        kind: 'tool_update',
        toolCallId: update.toolCallId,
        title: update.title ?? null,
        toolKind: update.kind ?? null,
        status: (update.status as NormalizedToolStatus | undefined | null) ?? null,
        parentToolCallId: null,
        diffs: extractDiffs(update.content ?? undefined),
        ...(outputText !== undefined ? { outputText } : {}),
        ...(terminalId !== undefined ? { terminalId } : {}),
        ...(locations !== undefined ? { locations } : {}),
      };
    }

    case 'plan': {
      return {
        kind: 'plan',
        entries: update.entries.map((e) => ({
          content: e.content,
          status: e.status,
          priority: e.priority,
        })),
      };
    }

    case 'config_option_update': {
      const raw = update as unknown as { configOptions?: unknown };
      const options = Array.isArray(raw.configOptions) ? raw.configOptions : [];
      return { kind: 'config', options };
    }

    case 'current_mode_update': {
      const raw = update as unknown as { currentModeId?: string };
      if (!raw.currentModeId) return { kind: 'ignored' };
      return { kind: 'mode_selected', modeId: raw.currentModeId };
    }

    case 'available_commands_update': {
      const raw = update as unknown as { availableCommands?: unknown };
      const commands = Array.isArray(raw.availableCommands) ? raw.availableCommands : [];
      return { kind: 'commands', commands };
    }

    case 'usage_update': {
      const raw = update as unknown as {
        used?: number;
        size?: number;
        cost?: { amount?: number; currency?: string } | null;
      };
      const contextUsed = raw.used ?? 0;
      const contextSize = raw.size ?? 0;
      const cost =
        raw.cost && typeof raw.cost.amount === 'number' && raw.cost.currency
          ? { amount: raw.cost.amount, currency: raw.cost.currency }
          : null;
      const rateLimit = decodeRateLimit(
        (update as { _meta?: Record<string, unknown> | null })._meta?.['_claude/rateLimit']
      );
      return {
        kind: 'usage',
        usage: { contextUsed, contextSize, cost, ...(rateLimit ? { rateLimit } : {}) },
      };
    }

    case 'session_info_update': {
      const raw = update as unknown as { title?: string };
      if (!raw.title) return { kind: 'ignored' };
      return { kind: 'title', title: raw.title };
    }

    case 'plan_update': {
      // Experimental ACP plan formats. Item plans replace the entries; a
      // markdown or file plan is shown as one entry so it is never lost.
      const plan = (
        update as unknown as {
          plan?: { type?: unknown; entries?: unknown; content?: unknown; uri?: unknown };
        }
      ).plan;
      if (!plan || typeof plan !== 'object') return { kind: 'ignored' };
      if (plan.type === 'items') return { kind: 'plan', entries: planEntries(plan.entries) };
      const text =
        plan.type === 'markdown' && typeof plan.content === 'string'
          ? plan.content
          : plan.type === 'file' && typeof plan.uri === 'string'
            ? `Plan: ${plan.uri}`
            : null;
      if (!text) return { kind: 'ignored' };
      return {
        kind: 'plan',
        entries: [{ content: text, status: 'in_progress', priority: 'medium' }],
      };
    }

    case 'plan_removed':
      return { kind: 'plan', entries: [] };

    default:
      return { kind: 'ignored' };
  }
}
