import type { SegmentCtx } from '@core/units';
import { describe, expect, it } from 'vitest';
import type { ToolNode } from '@/model';
import { toolFromItem } from './tool.def';

function searchItem(
  query: string,
  overrides: Partial<Extract<ToolNode, { kind: 'search-tool-call' }>> = {}
) {
  return {
    kind: 'search-tool-call',
    id: 'search-1',
    seq: 0,
    toolCallId: 'call-1',
    title: 'Search',
    status: 'done',
    query,
    ...overrides,
  } satisfies Extract<ToolNode, { kind: 'search-tool-call' }>;
}

function unknownItem(overrides: Partial<Extract<ToolNode, { kind: 'unknown-tool-call' }>> = {}) {
  return {
    kind: 'unknown-tool-call',
    id: 'unknown-1',
    seq: 0,
    toolCallId: 'call-unknown',
    title: 'Vendor tool',
    status: 'done',
    toolKind: 'other',
    name: 'Vendor tool',
    ...overrides,
  } satisfies Extract<ToolNode, { kind: 'unknown-tool-call' }>;
}

const ctx = {
  pendingToolCallIds: () => new Set<string>(),
} as SegmentCtx;

describe('toolFromItem', () => {
  it('preserves raw search queries that begin with search', () => {
    expect(toolFromItem(searchItem('search engine optimization'), ctx)).toMatchObject({
      name: 'Searched',
      inputSummary: 'search engine optimization',
    });
  });

  it('preserves search summaries without the redundant prefix', () => {
    expect(toolFromItem(searchItem('SolidJS virtualized list patterns'), ctx)).toMatchObject({
      name: 'Searched',
      inputSummary: 'SolidJS virtualized list patterns',
    });
  });

  it.each([
    ['running', 'Searching the web'],
    ['done', 'Searched the web'],
    ['error', 'Web search failed'],
  ] as const)('uses plain-language web-search copy for %s status', (status, name) => {
    expect(
      toolFromItem(
        searchItem('Web search: current STEP interchange standard', {
          title: 'Web search: current STEP interchange standard',
          status,
        }),
        ctx
      )
    ).toMatchObject({
      activity: 'web-search',
      name,
      inputSummary: 'current STEP interchange standard',
    });
  });

  it('uses the normalized web scope when provider titles do not identify the search domain', () => {
    expect(
      toolFromItem(
        searchItem('current STEP interchange standard', {
          title: 'current STEP interchange standard',
          scope: 'web',
          status: 'running',
        }),
        ctx
      )
    ).toMatchObject({
      activity: 'web-search',
      name: 'Searching the web',
      inputSummary: 'current STEP interchange standard',
    });
  });

  it('recognizes Claude WebSearch rows that were historically reported as fetches', () => {
    const item = {
      kind: 'web-fetch-tool-call',
      id: 'fetch-search-1',
      seq: 0,
      toolCallId: 'call-fetch-search',
      title: '"latest CAD kernel release"',
      status: 'running',
      url: '"latest CAD kernel release"',
    } satisfies Extract<ToolNode, { kind: 'web-fetch-tool-call' }>;

    expect(toolFromItem(item, ctx)).toMatchObject({
      activity: 'web-search',
      name: 'Searching the web',
      inputSummary: 'latest CAD kernel release',
    });
  });

  it.each([
    ['running', 'Generating image'],
    ['done', 'Generated image'],
    ['error', 'Image generation failed'],
  ] as const)(
    'surfaces image generation without internal ACP copy for %s status',
    (status, name) => {
      expect(
        toolFromItem(
          unknownItem({
            title: 'Image generation',
            name: 'Image generation',
            toolKind: 'other',
            status,
          }),
          ctx
        )
      ).toMatchObject({
        activity: 'image-generation',
        name,
        inputSummary: undefined,
      });
    }
  );

  it('recognizes image generation routed through an MCP integration', () => {
    const item = {
      kind: 'mcp-tool-call',
      id: 'image-mcp-1',
      seq: 0,
      toolCallId: 'call-image-mcp',
      title: 'imagegen',
      status: 'running',
      server: 'image_gen',
      tool: 'imagegen',
      inputSummary: 'A concept sketch of a compact gearbox',
    } satisfies Extract<ToolNode, { kind: 'mcp-tool-call' }>;

    expect(toolFromItem(item, ctx)).toMatchObject({
      activity: 'image-generation',
      name: 'Generating image',
      inputSummary: 'A concept sketch of a compact gearbox',
    });
  });

  it('carries generated image references without inlining their bytes', () => {
    const item = {
      ...unknownItem({
        title: 'Image generation',
        name: 'Image generation',
      }),
      attachments: [
        {
          id: 'attachment-generated-1',
          name: 'gearbox.png',
          mimeType: 'image/png' as const,
        },
      ],
    } as ToolNode;

    expect(toolFromItem(item, ctx)).toMatchObject({
      activity: 'image-generation',
      outputAttachments: [
        {
          id: 'attachment-generated-1',
          name: 'gearbox.png',
          mimeType: 'image/png',
        },
      ],
    });
  });

  it('names the integration and tool without exposing transport jargon', () => {
    const item = {
      kind: 'mcp-tool-call',
      id: 'notion-mcp-1',
      seq: 0,
      toolCallId: 'call-notion-mcp',
      title: 'search_pages',
      status: 'done',
      server: 'notion',
      tool: 'search_pages',
      inputSummary: '{"query":"bearing options"}',
    } satisfies Extract<ToolNode, { kind: 'mcp-tool-call' }>;

    expect(toolFromItem(item, ctx)).toMatchObject({
      activity: 'integration',
      name: 'Used Notion',
      inputSummary: 'Search pages',
    });
  });

  it('cleans up legacy MCP rows already stored as unknown tools', () => {
    expect(
      toolFromItem(
        unknownItem({
          title: 'mcp__linear__startup',
          name: 'mcp__linear__startup',
          toolKind: 'mcp__linear__startup',
        }),
        ctx
      )
    ).toMatchObject({
      activity: 'integration',
      name: 'Used Linear',
      inputSummary: 'Startup',
    });
  });

  it('does not expose the provider-internal other kind for generic tools', () => {
    expect(toolFromItem(unknownItem(), ctx)).toMatchObject({
      name: 'Vendor tool',
      inputSummary: undefined,
    });
  });
});
