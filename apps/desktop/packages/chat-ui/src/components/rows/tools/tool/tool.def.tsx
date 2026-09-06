import { ROW_H } from '@components/engine/row-metrics';
import type { SegmentCtx } from '@core/units';
import { defineUnit } from '@core/units';
import { pxTokens } from '@styles/px-tokens';
import { assignInlineVars } from '@vanilla-extract/dynamic';
import type { ChatImageAttachment, ChatToolCall, ToolNode } from '@/model';
import { Tool } from './Tool';
import { toolRoot, toolVars } from './tool.css';

type ToolPresentation = Pick<ChatToolCall, 'name' | 'activity' | 'inputSummary'>;

function statusLabel(
  status: ChatToolCall['status'],
  labels: { running: string; done: string; error: string }
): string {
  return labels[status];
}

function cleanSearchSummary(value: string): string {
  const withoutPrefix = value.replace(/^web\s+search:\s*/i, '').trim();
  if (withoutPrefix.length >= 2 && withoutPrefix.startsWith('"') && withoutPrefix.endsWith('"')) {
    return withoutPrefix.slice(1, -1);
  }
  return withoutPrefix;
}

function isImageGenerationTool(item: ToolNode): boolean {
  if (item.kind === 'tool-group') return false;
  const signature = [
    item.title,
    item.kind === 'unknown-tool-call' ? item.name : '',
    item.kind === 'unknown-tool-call' ? item.toolKind : '',
    item.kind === 'mcp-tool-call' ? item.server : '',
    item.kind === 'mcp-tool-call' ? item.tool : '',
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return (
    signature.includes('image generation') ||
    /(?:^|[\s._:/-])image[_-]?gen(?:eration)?(?:$|[\s._:/-])/.test(signature) ||
    /(?:^|[\s._:/-])imagegen(?:$|[\s._:/-])/.test(signature)
  );
}

function isWebSearchItem(item: ToolNode): boolean {
  if (item.kind === 'tool-group') return false;
  if (item.kind === 'search-tool-call' && item.scope === 'web') return true;
  const title = item.title.trim();
  if (/^(?:web\s+search|open\s+page|find\s+in\s+page)\b/i.test(title)) return true;
  if (item.kind === 'unknown-tool-call') {
    return /^(?:web[_ -]?search|browser\s+search)$/i.test(item.name.trim());
  }
  // Claude historically reported WebSearch as `fetch` with a quoted query,
  // while real WebFetch calls are titled `Fetch <url>`.
  return item.kind === 'web-fetch-tool-call' && /^".*"$/.test(title);
}

function humanizeToolName(value: string): string {
  const leaf = value.split(/\.|__/).filter(Boolean).at(-1) ?? value;
  const words = leaf.replace(/[_-]+/g, ' ').trim();
  return words ? `${words[0]!.toUpperCase()}${words.slice(1)}` : 'integration';
}

function integrationIdentity(item: ToolNode): {
  server: string;
  tool: string;
} | null {
  if (item.kind === 'mcp-tool-call') {
    return {
      server: item.server ?? item.tool,
      tool: item.tool,
    };
  }
  if (item.kind !== 'unknown-tool-call') return null;
  const match = /^mcp__([\s\S]+?)__([\s\S]+)$/.exec(item.name);
  if (!match?.[1] || !match[2]) return null;
  return { server: match[1], tool: match[2] };
}

function toolPresentation(item: ToolNode): ToolPresentation {
  const status = 'status' in item ? item.status : 'done';

  if (item.kind === 'tool-group') return { name: item.label };

  if (isImageGenerationTool(item)) {
    return {
      activity: 'image-generation',
      name: statusLabel(status, {
        running: 'Generating image',
        done: 'Generated image',
        error: 'Image generation failed',
      }),
      inputSummary: 'inputSummary' in item ? item.inputSummary : undefined,
    };
  }

  if (isWebSearchItem(item)) {
    const rawSummary =
      item.kind === 'search-tool-call'
        ? item.query
        : item.kind === 'web-fetch-tool-call'
          ? (item.pageTitle ?? item.url)
          : item.title;
    return {
      activity: 'web-search',
      name: statusLabel(status, {
        running: 'Searching the web',
        done: 'Searched the web',
        error: 'Web search failed',
      }),
      inputSummary: cleanSearchSummary(rawSummary),
    };
  }

  if (item.kind === 'search-tool-call') {
    return {
      activity: 'search',
      name: statusLabel(status, {
        running: 'Searching',
        done: 'Searched',
        error: 'Search failed',
      }),
      inputSummary: `${cleanSearchSummary(item.query)}${
        item.matchCount !== undefined ? ` (${item.matchCount} matches)` : ''
      }`,
    };
  }

  if (item.kind === 'web-fetch-tool-call') {
    return {
      activity: 'web-fetch',
      name: statusLabel(status, {
        running: 'Opening page',
        done: 'Opened page',
        error: 'Page fetch failed',
      }),
      inputSummary: (item.pageTitle ?? item.url).replace(/^fetch\s+/i, ''),
    };
  }

  const integration = integrationIdentity(item);
  if (integration) {
    const integrationName = humanizeToolName(integration.server);
    const toolName = humanizeToolName(integration.tool);
    return {
      activity: 'integration',
      name: statusLabel(status, {
        running: `Using ${integrationName}`,
        done: `Used ${integrationName}`,
        error: `${integrationName} failed`,
      }),
      // Provider-native MCP arguments may contain credentials or private payloads.
      // The activity row identifies the integration and action without echoing them.
      inputSummary: toolName,
    };
  }

  const name =
    item.kind === 'spawn-subagent-tool-call'
      ? 'Subagent'
      : item.kind === 'unknown-tool-call'
        ? item.name
        : 'Tool';
  const inputSummary =
    item.kind === 'spawn-subagent-tool-call'
      ? `${item.name}${item.background ? ' (background)' : ''}`
      : item.kind === 'unknown-tool-call'
        ? (item.inputSummary ??
          (item.toolKind &&
          item.toolKind !== item.name &&
          !['other', 'unknown', 'think'].includes(item.toolKind)
            ? item.toolKind
            : undefined))
        : 'inputSummary' in item
          ? item.inputSummary
          : undefined;
  return { name, inputSummary };
}

function outputAttachmentsFromItem(item: ToolNode): ChatImageAttachment[] | undefined {
  if (item.kind === 'tool-group') return undefined;
  const attachments = item.attachments;
  if (!attachments?.length) return undefined;
  return attachments.map((attachment) => ({
    id: attachment.id,
    name: attachment.name,
    ...(attachment.mimeType ? { mimeType: attachment.mimeType } : {}),
  }));
}

const OUTPUT_PREVIEW_LIMIT = 160;

/**
 * The first line of a text result. Integration (MCP) results stay hidden:
 * their payloads may carry credentials.
 */
function outputPreviewFromItem(item: ToolNode): string | undefined {
  if (item.kind === 'tool-group' || item.kind === 'mcp-tool-call') return undefined;
  const text = item.outputText;
  if (!text) return undefined;
  const line = text
    .split(/\r?\n/)
    .map((candidate) => candidate.trim())
    .find(Boolean);
  if (!line) return undefined;
  return line.length > OUTPUT_PREVIEW_LIMIT ? `${line.slice(0, OUTPUT_PREVIEW_LIMIT - 1)}…` : line;
}

export function toolFromItem(item: ToolNode, ctx: SegmentCtx): ChatToolCall {
  const base = 'toolCallId' in item ? item : null;
  const presentation = toolPresentation(item);
  const running = 'status' in item && item.status === 'running';
  const progress = base?.progress;
  const outputPreview = running && progress ? progress : outputPreviewFromItem(item);
  return {
    kind: 'tool',
    id: item.id,
    name: presentation.name,
    status: 'status' in item ? item.status : 'done',
    ...(presentation.activity ? { activity: presentation.activity } : {}),
    awaitingPermission: base ? ctx.pendingToolCallIds().has(base.toolCallId) : false,
    ...(base?.error ? { error: base.error } : {}),
    inputSummary: presentation.inputSummary,
    ...(outputPreview ? { outputPreview } : {}),
    outputAttachments: outputAttachmentsFromItem(item),
  };
}

function toolUnitH(data: ChatToolCall, lineHeight: number, rowH: number): number {
  return rowH + (data.outputPreview ? lineHeight : 0);
}

export const toolUnitDef = defineUnit<ChatToolCall, { rowH: number }>({
  kind: 'tool',
  margin: { top: 2, bottom: 2 },
  vars: { rowH: ROW_H },

  measure(data, ctx, vars): number {
    return toolUnitH(data, ctx.theme.fonts.body.lineHeight, vars.rowH);
  },

  Render(props) {
    const height = () => {
      const ctx = props.ctx.measureCtx?.();
      return toolUnitH(props.data, ctx?.theme.fonts.body.lineHeight ?? 20, props.vars.rowH);
    };
    return (
      <div class={toolRoot} style={assignInlineVars(toolVars, pxTokens({ rowH: height() }))}>
        <Tool item={props.data} />
      </div>
    );
  },
});
