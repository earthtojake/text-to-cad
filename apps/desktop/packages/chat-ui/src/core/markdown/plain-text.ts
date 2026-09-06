/**
 * plain-text — extract a plain-text string from a Block.
 *
 * Used for a11y mirrors (sr-only) in message rows. Each block kind produces a
 * human-readable string without any markdown syntax or HTML.
 *
 * This module is PURE: no geometry, no pretext/fonts, no DOM imports.
 */

import type { Block, InlineRun, ProseBlock } from './document';

function inlineRunText(run: InlineRun): string {
  if (run.kind === 'text') return run.text;
  if (run.kind === 'code') return run.text;
  if (run.kind === 'mention') return run.label;
  return ''; // break
}

export function blockPlainText(block: Block): string {
  if (block.kind === 'prose') {
    return (block as ProseBlock).runs.map(inlineRunText).join('');
  }
  if (block.kind === 'code') return block.code;
  if (block.kind === 'mermaid') return block.source;
  if (block.kind === 'table') {
    const allRows = [block.header, ...block.rows];
    return allRows.map((row) => row.join(' | ')).join('\n');
  }
  return '';
}
