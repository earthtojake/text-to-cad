/**
 * layoutProse / measureProseNaturalWidth — pure geometry for a ProseBlock.
 *
 * Moved here from core/layout/layout-prose.ts so that layout logic lives
 * alongside the Prose renderer.  No DOM access; uses pretext for text shaping.
 *
 * Break semantics:
 *   InlineRun[] may contain `{ kind: 'break' }` entries. These are treated as
 *   explicit line boundaries: the run array is split into segments at each
 *   break, each segment is shaped independently by pretext, and the produced
 *   lines are stacked in global line-index order. An empty segment (adjacent
 *   breaks) advances the global line counter by one (blank line).
 */

import {
  materializeRichInlineLineRange,
  measureRichInlineStats,
  type PreparedRichInline,
  type RichInlineItem,
  prepareRichInline as rawPrepareRichInline,
  walkRichInlineLineRanges,
} from '@chenglou/pretext/rich-inline';
import type { FontConfig } from '@core/config';
import type {
  FragmentLayout,
  LineLayout,
  BulletLayout,
  ProseLaidOut,
} from '@core/layout/layout-types';
import type { InlineRun, ProseBlock } from '@core/markdown/document';
import { runsToRichItems } from '@core/measure/to-rich-items';
import { BLOCKQUOTE_INDENT, LIST_BULLET_GAP, LIST_INDENT } from './geometry';

type PrepareRichInlineFn = (items: RichInlineItem[]) => PreparedRichInline;

const UNBOUNDED_WIDTH = 1e7;

function lineHeightForVariant(variant: ProseBlock['variant'], fonts: FontConfig): number {
  switch (variant) {
    case 'h1':
      return fonts.h1.lineHeight;
    case 'h2':
      return fonts.h2.lineHeight;
    case 'h3':
    case 'h4':
    case 'h5':
    case 'h6':
      return fonts.h3.lineHeight;
    default:
      return fonts.body.lineHeight;
  }
}

function proseIndent(block: ProseBlock): { indent: number; textLeft: number } {
  const depth = block.depth ?? 0;
  const isListItem = block.variant === 'list-item';
  const isQuote = block.variant === 'quote';
  const indentPerLevel = isListItem ? LIST_INDENT : isQuote ? BLOCKQUOTE_INDENT : 0;
  const indent = (depth + 1) * indentPerLevel;
  const textLeft = isListItem ? indent + LIST_BULLET_GAP : indent;
  return { indent, textLeft };
}

/**
 * Split a run array into segments, breaking at every InlineBreak run.
 * Returns an array of sub-arrays; each sub-array holds the original run
 * indices alongside non-break runs so runIndex in FragmentLayout maps back
 * correctly into the full `block.runs` array.
 */
function segmentRuns(runs: InlineRun[]): Array<{ segRuns: InlineRun[]; baseIndex: number }[]> {
  const segments: Array<{ segRuns: InlineRun[]; baseIndex: number }[]> = [];
  let current: { segRuns: InlineRun[]; baseIndex: number }[] = [];

  for (let i = 0; i < runs.length; i++) {
    const run = runs[i];
    if (run.kind === 'break') {
      segments.push(current);
      current = [];
    } else {
      current.push({ segRuns: [run], baseIndex: i });
    }
  }
  segments.push(current);
  return segments;
}

export function measureProseNaturalWidth(
  block: ProseBlock,
  fonts: FontConfig,
  prepareRichInline: PrepareRichInlineFn = rawPrepareRichInline
): number {
  if (block.runs.length === 0) return 0;
  const { textLeft } = proseIndent(block);
  const segments = segmentRuns(block.runs);
  let maxWidth = 0;
  for (const seg of segments) {
    if (seg.length === 0) continue;
    const items = runsToRichItems(
      seg.map((s) => s.segRuns[0]),
      fonts,
      block.variant
    );
    const prepared = prepareRichInline(items);
    const stats = measureRichInlineStats(prepared, UNBOUNDED_WIDTH);
    maxWidth = Math.max(maxWidth, textLeft + stats.maxLineWidth);
  }
  return maxWidth;
}

export function layoutProse(
  block: ProseBlock,
  width: number,
  fonts: FontConfig,
  blockTop: number,
  prepareRichInline: PrepareRichInlineFn = rawPrepareRichInline
): ProseLaidOut {
  const lineHeight = lineHeightForVariant(block.variant, fonts);

  if (block.runs.length === 0) {
    return {
      kind: 'prose',
      id: block.id,
      top: blockTop,
      height: 0,
      contentWidth: 0,
      lineHeight,
      lines: [],
    };
  }

  const isQuote = block.variant === 'quote';
  const isListItem = block.variant === 'list-item';
  const { indent, textLeft } = proseIndent(block);
  const effectiveWidth = Math.max(1, width - textLeft);

  const segments = segmentRuns(block.runs);

  const lines: LineLayout[] = [];
  let globalLine = 0;
  let maxRight = 0;

  for (const seg of segments) {
    if (seg.length === 0) {
      // Blank line (consecutive breaks or leading/trailing break).
      globalLine++;
      continue;
    }

    // Build the index-remapping table: pretext item index → original run index.
    const segRunList = seg.map((s) => s.segRuns[0]);
    const indexMap = seg.map((s) => s.baseIndex);

    const items = runsToRichItems(segRunList, fonts, block.variant);
    const prepared = prepareRichInline(items);

    walkRichInlineLineRanges(prepared, effectiveWidth, (range) => {
      const line = materializeRichInlineLineRange(prepared, range);
      let x = 0;
      const frags: FragmentLayout[] = [];

      for (const f of line.fragments) {
        x += f.gapBefore;
        // Map from per-segment item index back to original block.runs index.
        frags.push({ text: f.text, x, runIndex: indexMap[f.itemIndex] ?? f.itemIndex });
        x += f.occupiedWidth;
      }

      maxRight = Math.max(maxRight, textLeft + x);
      lines.push({ top: globalLine * lineHeight, left: textLeft, fragments: frags });
      globalLine++;
    });
  }

  const height = globalLine * lineHeight;

  let bullet: BulletLayout | undefined;
  if (isListItem) {
    bullet = {
      // Anchor at the indent line; the renderer centers the glyph on this point
      // (translate(-50%, -50%)) for true horizontal + vertical centering.
      x: indent,
      top: lineHeight / 2,
      char: '•',
    };
  }

  return {
    kind: 'prose',
    id: block.id,
    top: blockTop,
    height,
    contentWidth: maxRight,
    lineHeight,
    lines,
    bullet,
    quoteRail: isQuote,
  };
}
