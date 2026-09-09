/**
 * to-rich-items — Convert InlineRun[] to the RichInlineItem[] format that pretext expects.
 *
 * Bridges the markdown document model (InlineRun) and the measurement tier
 * (pretext / FontConfig). Lives in core/measure/ because it depends on both
 * pretext and FontConfig — keeping it out of core/markdown/ preserves that
 * module as a pure, dependency-free document model.
 *
 * Mention icon geometry (mentionIconW, mentionIconGap) is now read from the
 * FontConfig passed in so there is no import-time coupling to the Prose renderer.
 */

import type { RichInlineItem } from '@chenglou/pretext/rich-inline';
import type { FontConfig } from '@core/config';
import { mentionDisplayText } from '@core/markdown/document';
import type {
  InlineCode,
  InlineMention,
  InlineRun,
  InlineText,
  ProseVariant,
} from '@core/markdown/document';

/**
 * Returns the heading font shorthand for heading variants, or null for non-headings.
 *
 * In a heading, every inline run (regardless of bold/italic/code/mention) is rendered
 * with the heading font and no chip chrome — matching Prose.tsx's fragKey blanket
 * `pf--${variant}` return for heading variants. Passing the variant here ensures
 * the pretext measurement uses the same font as the renderer, preventing line-wrap
 * discrepancies (and thus reserved-height mismatches) for long headings.
 */
function headingFontForVariant(
  variant: ProseVariant | undefined,
  fonts: FontConfig
): string | null {
  switch (variant) {
    case 'h1':
      return fonts.h1.font;
    case 'h2':
      return fonts.h2.font;
    case 'h3':
    case 'h4':
    case 'h5':
    case 'h6':
      return fonts.h3.font;
    default:
      return null;
  }
}

export function runsToRichItems(
  runs: InlineRun[],
  fonts: FontConfig,
  variant?: ProseVariant
): RichInlineItem[] {
  const headingFont = headingFontForVariant(variant, fonts);

  return runs.flatMap((run): RichInlineItem[] => {
    // Break markers are segment boundaries in layoutProse; they have no glyph.
    if (run.kind === 'break') return [];

    // In heading variants all runs use the heading font — no chip padding, no
    // break:'never' constraint — mirroring the renderer's blanket heading class.
    if (headingFont !== null) {
      let text: string;
      if (run.kind === 'code') text = (run as InlineCode).text;
      else if (run.kind === 'mention') text = mentionDisplayText(run as InlineMention);
      else text = (run as InlineText).text;
      return text ? [{ text, font: headingFont }] : [];
    }

    if (run.kind === 'code') {
      return [
        {
          text: (run as InlineCode).text,
          font: fonts.inlineCode.font,
          break: 'never',
          extraWidth: fonts.inlineCodeExtraWidth,
        },
      ];
    }
    if (run.kind === 'mention') {
      const mention = run as InlineMention;
      // Resolved mentions display the short name and include extra space for the
      // leading icon container. fonts.mentionIconW + fonts.mentionIconGap must equal
      // the px values used in Prose.tsx so rendering and measurement stay in sync.
      const displayText = mentionDisplayText(mention);
      const iconWidth = mention.mentionKind ? fonts.mentionIconW + fonts.mentionIconGap : 0;
      return [
        {
          text: displayText,
          font: fonts.mention.font,
          break: 'never',
          extraWidth: fonts.mentionExtraWidth + iconWidth,
        },
      ];
    }
    const t = run as InlineText;
    let font = fonts.body.font;
    if (t.bold && t.italic) font = fonts.boldItalic.font;
    else if (t.bold) font = fonts.bold.font;
    else if (t.italic) font = fonts.italic.font;
    else if (t.href) font = fonts.link.font;
    return [{ text: t.text, font }];
  });
}
