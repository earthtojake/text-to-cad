/**
 * layoutCode — pure geometry for a CodeBlock.
 *
 * Moved here from core/layout/layout-code.ts so that layout constants,
 * CSS vars, and the renderer live in the same folder.
 *
 * Constants come from ./metrics (single source of truth).
 * Typography (line height) comes from the FontConfig passed in.
 */

import type { CodeLaidOut } from '@core/layout/layout-types';
import { reserveHeight } from '@core/layout/reserve-height';
import type { CodeBlock } from '@core/markdown/document';
import type { FontConfig } from '@core/measure/fonts';

const CODE_BLOCK_PAD_Y = 8;
const CODE_BLOCK_BORDER = 1;

export function layoutCode(
  block: CodeBlock,
  fonts: FontConfig,
  blockTop: number,
  effectiveWidth: number
): CodeLaidOut {
  const codeLineHeight = fonts.code.lineHeight;
  const rawLines = block.code.split('\n');

  const lines = rawLines.map((text, i) => ({
    top: CODE_BLOCK_PAD_Y + i * codeLineHeight,
    text,
  }));

  const height = reserveHeight({
    content: rawLines.length * codeLineHeight,
    padY: CODE_BLOCK_PAD_Y,
    border: CODE_BLOCK_BORDER,
  });

  return {
    kind: 'code',
    id: block.id,
    top: blockTop,
    height,
    contentWidth: effectiveWidth,
    lines,
    lang: block.lang,
  };
}
