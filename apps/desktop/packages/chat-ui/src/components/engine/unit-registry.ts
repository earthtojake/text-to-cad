/**
 * unit-registry — segmenter and unit-def registries for the flat unit engine.
 *
 * Two independent maps:
 *
 *   SEGMENTERS   — ChatItem.kind → ItemSegmenter
 *                  Defines how each transcript item is split into RenderUnits.
 *
 *   UNIT_REGISTRY — unit.kind → UnitDef
 *                   Defines how each unit kind is measured and rendered.
 *
 * Adding a new ChatItem kind:
 *   1. Implement a UnitDef<D> and an ItemSegmenter in the appropriate folder.
 *   2. Register the segmenter in SEGMENTERS.
 *   3. Register the UnitDef in UNIT_REGISTRY.
 */

import { generatedImageUnitDef } from '@components/rows/generated-image/generated-image.def';
import { messageFromItem, messageUnitDef } from '@components/rows/message/message.def';
import { planFromItem, planUnitDef } from '@components/rows/plan/plan.def';
import { resourceLinkUnitDef } from '@components/rows/resource-link/resource-link.def';
import { thinkingUnitDef } from '@components/rows/thinking/thinking.def';
import {
  createFileDiffFromItem,
  diffUnitDef,
  modifyFileDiffFromItem,
} from '@components/rows/tools/diff/diff.def';
import { executeFromItem, executeUnitDef } from '@components/rows/tools/execute/execute.def';
import {
  deleteFileOpFromItem,
  fileOpUnitDef,
  readFileOpFromItem,
} from '@components/rows/tools/file-op/file-op.def';
import { subagentFromItem, subagentUnitDef } from '@components/rows/tools/subagent/subagent.def';
import { toolGroupUnitDef } from '@components/rows/tools/tool-group/tool-group.def';
import { toolFromItem, toolUnitDef } from '@components/rows/tools/tool/tool.def';
import { turnOutcomeUnitDef } from '@components/rows/turn-outcome/turn-outcome.def';
import { workingUnitDef } from '@components/rows/working/working.def';
import type {
  GroupChrome,
  ItemSegmenter,
  RenderUnit,
  SegmentCtx,
  SegmentItem,
  UnitDef,
} from '@core/units';
import { unit } from '@core/units';
import type { ItemNode } from '@state/flatten';
import type {
  ChatDiff,
  ChatExecute,
  ChatFileOpToolCall,
  ChatGeneratedImage,
  ChatItem,
  ChatMessage,
  ChatPlan,
  ChatSubagentToolCall,
  ChatToolCall,
  SyntheticItem,
  ToolNode,
} from '@/model';
import { ROW_INSET_X } from './row-metrics';

// ── Native single-unit segmenter for composites ───────────────────────────────
//
// Each composite item becomes exactly one RenderUnit with chrome.insetX so
// the native UnitDef.measure receives the same effective width as Row.tsx used.

type ToolPresentationData =
  | ChatExecute
  | ChatFileOpToolCall
  | ChatDiff
  | ChatPlan
  | ChatSubagentToolCall
  | ChatToolCall;
type RegistryUnitDef = UnitDef<unknown, Record<string, number>>;

function nativePassthrough<T extends SegmentItem>(
  kind: string,
  toData: (item: T, ctx: SegmentCtx) => unknown,
  chrome?: GroupChrome
): ItemSegmenter {
  return {
    kind,
    chrome,
    segment: (item, ctx) => [unit(kind, item, toData(item as T, ctx), { key: 'self' })],
  };
}

/** Chrome shared by all non-user-message composite rows (matches legacy Row.tsx inset). */
const COMPOSITE_CHROME: GroupChrome = { insetX: ROW_INSET_X };

/**
 * User message chrome: full column width (no inset). The card border/padding/bg
 * are handled internally by UserMessageCard, so chrome carries only insetX=0.
 */
const USER_CHROME: GroupChrome = { insetX: 0 };

/**
 * Role-aware message segmenter.
 *
 * Each message becomes exactly one unit with key='self'. The chrome is set
 * per-unit (not on the segmenter) so flatten.ts does not overwrite it with a
 * single shared value — user messages get USER_CHROME (full width), all others
 * get COMPOSITE_CHROME (insetX=ROW_INSET_X).
 */
const messageSegmenter: ItemSegmenter = {
  kind: 'message',
  // No top-level chrome: we set u.chrome per-unit in segment() below so
  // flatten's chrome-copy pass (which only fires when seg.chrome is truthy)
  // cannot overwrite the per-role value we assigned.
  segment: (item, ctx) => {
    const data = messageFromItem(item as ChatMessage, ctx);
    const u = unit('message', item, data, { key: 'self' });
    u.chrome = data.role === 'user' ? USER_CHROME : COMPOSITE_CHROME;
    if (data.role === 'user' || !data.attachments?.length) return [u];
    const image = unit(
      'generated-image',
      item,
      {
        kind: 'generated-image',
        id: `${data.id}:attachments`,
        attachments: data.attachments,
        sourceItemId: data.id,
        source: 'assistant-message',
      } satisfies ChatGeneratedImage,
      { key: 'attachments' }
    );
    image.chrome = COMPOSITE_CHROME;
    return [u, image];
  },
};

function imageResultFromTool(
  tool: ChatToolCall,
  seenAttachmentIds = new Set<string>()
): ChatGeneratedImage | null {
  const attachments = tool.outputAttachments?.filter((attachment) => {
    if (seenAttachmentIds.has(attachment.id)) return false;
    seenAttachmentIds.add(attachment.id);
    return true;
  });
  if (!attachments?.length) return null;
  return {
    kind: 'generated-image',
    id: `${tool.id}:output`,
    attachments,
    sourceItemId: tool.id,
    source: 'generated-image',
  };
}

function toolTreeImageUnits(root: ToolNode, ctx: SegmentCtx): RenderUnit[] {
  const units: RenderUnit[] = [];
  const seenAttachmentIds = new Set<string>();

  const visit = (node: ToolNode) => {
    const image = imageResultFromTool(toolFromItem(node, ctx), seenAttachmentIds);
    if (image) {
      units.push(
        unit('generated-image', root, image, {
          key: `generated-image:${node.id}`,
        })
      );
    }
    for (const child of node.children ?? []) visit(child);
  };

  visit(root);
  return units;
}

function toToolGroupNode(item: ToolNode, ctx: SegmentCtx): ItemNode {
  const header = item.kind === 'tool-group' ? toolFromItem(item, ctx) : toUnitData(item, ctx);
  const children =
    item.kind === 'tool-group'
      ? item.children.map((child: ToolNode) => toToolGroupNode(child, ctx))
      : 'children' in item && item.children
        ? item.children.map((child: ToolNode) => toToolGroupNode(child, ctx))
        : [];
  return { item: header, children };
}

function toUnitData(item: ToolNode, ctx: SegmentCtx): ToolPresentationData {
  switch (item.kind) {
    case 'execute-tool-call':
      return executeFromItem(item, ctx);
    case 'read-tool-call':
      return readFileOpFromItem(item, ctx);
    case 'create-file-tool-call':
      return createFileDiffFromItem(item, ctx);
    case 'modify-file-tool-call':
      return modifyFileDiffFromItem(item, ctx);
    case 'delete-file-tool-call':
      return deleteFileOpFromItem(item, ctx);
    case 'create-plan-tool-call':
      return planFromItem(item, ctx);
    case 'spawn-subagent-tool-call':
      return subagentFromItem(item, ctx);
    case 'tool-group':
      return toolFromItem(item, ctx);
    default:
      return toolFromItem(item, ctx);
  }
}

function toolNodeSegment(kind: ToolNode['kind']): ItemSegmenter {
  return {
    kind,
    chrome: COMPOSITE_CHROME,
    segment(item, ctx) {
      const tool = item as ToolNode;
      const children = tool.children;
      if (children && children.length > 0) {
        return [
          unit('tool-group', tool, toToolGroupNode(tool, ctx), { key: 'self' }),
          ...toolTreeImageUnits(tool, ctx),
        ];
      }
      const data = toUnitData(tool, ctx);
      return [unit(data.kind, tool, data, { key: 'self' }), ...toolTreeImageUnits(tool, ctx)];
    },
  };
}

const toolSegmenter: ItemSegmenter = {
  kind: 'tool',
  chrome: COMPOSITE_CHROME,
  segment(item) {
    const tool = item as ChatToolCall;
    const units: RenderUnit[] = [unit('tool', tool, tool, { key: 'self' })];
    const image = imageResultFromTool(tool);
    if (image) units.push(unit('generated-image', tool, image, { key: 'generated-image' }));
    return units;
  },
};

// ── SEGMENTERS ────────────────────────────────────────────────────────────────

/**
 * Maps ChatItem.kind to its ItemSegmenter.
 *
 * Composites use nativePassthrough with COMPOSITE_CHROME so that their native
 * UnitDef.measure receives the same effective width as the old Row.tsx path
 * (rowWidth - 2 * ROW_INSET_X). The chrome.insetX is applied visually by
 * UnitRow and subtracted from rowWidth before nativeMeasureCtx.
 */
export const SEGMENTERS: Record<string, ItemSegmenter> = {
  message: messageSegmenter,
  thinking: nativePassthrough<ChatItem>('thinking', (item) => item, COMPOSITE_CHROME),
  tool: toolSegmenter,
  'generated-image': nativePassthrough<ChatItem>(
    'generated-image',
    (item) => item,
    COMPOSITE_CHROME
  ),
  'file-op': nativePassthrough<ChatItem>('file-op', (item) => item, COMPOSITE_CHROME),
  execute: nativePassthrough<ChatItem>('execute', (item) => item, COMPOSITE_CHROME),
  diff: nativePassthrough<ChatItem>('diff', (item) => item, COMPOSITE_CHROME),
  plan: nativePassthrough<ChatItem>('plan', (item) => item, COMPOSITE_CHROME),
  subagent: nativePassthrough<ChatItem>('subagent', (item) => item, COMPOSITE_CHROME),
  'resource-link': nativePassthrough<ChatItem>('resource-link', (item) => item, COMPOSITE_CHROME),
  'execute-tool-call': toolNodeSegment('execute-tool-call'),
  'read-tool-call': toolNodeSegment('read-tool-call'),
  'create-file-tool-call': toolNodeSegment('create-file-tool-call'),
  'modify-file-tool-call': toolNodeSegment('modify-file-tool-call'),
  'delete-file-tool-call': toolNodeSegment('delete-file-tool-call'),
  'search-tool-call': toolNodeSegment('search-tool-call'),
  'mcp-tool-call': toolNodeSegment('mcp-tool-call'),
  'web-fetch-tool-call': toolNodeSegment('web-fetch-tool-call'),
  'spawn-subagent-tool-call': toolNodeSegment('spawn-subagent-tool-call'),
  'create-plan-tool-call': toolNodeSegment('create-plan-tool-call'),
  'unknown-tool-call': toolNodeSegment('unknown-tool-call'),
  'tool-group': toolNodeSegment('tool-group'),
  working: nativePassthrough<SyntheticItem>('working', (item) => item, COMPOSITE_CHROME),
  'turn-outcome': nativePassthrough<SyntheticItem>(
    'turn-outcome',
    (item) => item,
    COMPOSITE_CHROME
  ),
};

// ── UNIT_REGISTRY ─────────────────────────────────────────────────────────────

/**
 * Maps unit.kind to its UnitDef.
 *
 * message: single-unit def; measure/Render handle block layout internally.
 * Composite item unit defs also handle their own internal layout.
 */
export const UNIT_REGISTRY: Record<string, RegistryUnitDef> = {
  // Message unit (single unit per message, renders block stack internally)
  message: messageUnitDef as unknown as RegistryUnitDef,
  // Composite item units (single-unit per ChatItem kind)
  diff: diffUnitDef as unknown as RegistryUnitDef,
  plan: planUnitDef as unknown as RegistryUnitDef,
  thinking: thinkingUnitDef as unknown as RegistryUnitDef,
  'file-op': fileOpUnitDef as unknown as RegistryUnitDef,
  subagent: subagentUnitDef as unknown as RegistryUnitDef,
  tool: toolUnitDef as unknown as RegistryUnitDef,
  'generated-image': generatedImageUnitDef as unknown as RegistryUnitDef,
  execute: executeUnitDef as unknown as RegistryUnitDef,
  'resource-link': resourceLinkUnitDef as unknown as RegistryUnitDef,
  // Hierarchical composite: parent tool call with nested children
  'tool-group': toolGroupUnitDef as unknown as RegistryUnitDef,
  working: workingUnitDef as unknown as RegistryUnitDef,
  'turn-outcome': turnOutcomeUnitDef as unknown as RegistryUnitDef,
};
