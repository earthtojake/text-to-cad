import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

// ── Geometry (feeds pretext measurement — do not change without updating metrics.ts) ──

/** A pre-laid-out line row. Height is set via inline style from the line-height constant. */
export const pline = style({
  position: 'absolute',
  display: 'flex',
  alignItems: 'baseline',
});

/**
 * white-space: pre and line-height: 1 feed pretext and must NOT be changed to utility classes.
 * top:50% + translateY(-50%) centers each fragment within its line band.
 */
export const pf = style({
  display: 'inline-block',
  whiteSpace: 'pre',
  lineHeight: 1,
  position: 'absolute',
  top: '50%',
  transform: 'translateY(-50%)',
});

export const pfBody = style({
  fontSize: vars.typeBodyFontSize,
  fontWeight: vars.typeBodyFontWeight,
  fontFamily: vars.typeBodyFontFamily,
});

export const pfBold = style({
  fontSize: vars.typeBodyFontSize,
  fontWeight: vars.typeBodyBoldFontWeight,
  fontFamily: vars.typeBodyFontFamily,
});

export const pfItalic = style({
  fontSize: vars.typeBodyFontSize,
  fontWeight: vars.typeBodyFontWeight,
  fontStyle: 'italic',
  fontFamily: vars.typeBodyFontFamily,
});

export const pfBoldItalic = style({
  fontSize: vars.typeBodyFontSize,
  fontWeight: vars.typeBodyBoldFontWeight,
  fontStyle: 'italic',
  fontFamily: vars.typeBodyFontFamily,
});

export const pfLink = style({
  fontSize: vars.typeBodyFontSize,
  fontWeight: vars.typeBodyLinkFontWeight,
  fontFamily: vars.typeBodyFontFamily,
  // color, text-decoration, cursor — applied in Prose.tsx via visual classes
});

export const pfH1 = style({
  fontSize: vars.typeH1FontSize,
  fontWeight: vars.typeH1FontWeight,
  fontFamily: vars.typeH1FontFamily,
});

export const pfH2 = style({
  fontSize: vars.typeH2FontSize,
  fontWeight: vars.typeH2FontWeight,
  fontFamily: vars.typeH2FontFamily,
});

/** h3–h6 share the h3 scale. */
export const pfH3 = style({
  fontSize: vars.typeH3FontSize,
  fontWeight: vars.typeH3FontWeight,
  fontFamily: vars.typeH3FontFamily,
});

/** Inline code chip — font metrics and padding feed pretext measurement. */
export const pfInlineCode = style({
  fontSize: vars.typeInlineCodeFontSize,
  fontWeight: vars.typeInlineCodeFontWeight,
  fontFamily: vars.typeInlineCodeFontFamily,
  paddingLeft: vars.icPadX,
  paddingRight: vars.icPadX,
  // Fixed 16px chip height (body lineHeight 20px * 0.8), border-box so padding is included.
  // pf's top:50%/translateY(-50%) centers the chip in the 20px line band.
  height: `calc(${vars.typeBodyLineHeight} * 0.8)`,
  boxSizing: 'border-box',
  display: 'inline-flex',
  alignItems: 'center',
});

export const pfMention = style({
  fontSize: vars.typeMentionFontSize,
  fontWeight: vars.typeMentionFontWeight,
  fontFamily: vars.typeMentionFontFamily,
  paddingLeft: vars.mentionPadX,
  paddingRight: vars.mentionPadX,
  // Fixed 16px chip height (body lineHeight 20px * 0.8), border-box so padding is included.
  // pf's top:50%/translateY(-50%) centers the chip in the 20px line band.
  height: `calc(${vars.typeBodyLineHeight} * 0.8)`,
  boxSizing: 'border-box',
  display: 'inline-flex',
  alignItems: 'center',
});

export const pfVariants: Record<string, string> = {
  'pf--body': pfBody,
  'pf--bold': pfBold,
  'pf--italic': pfItalic,
  'pf--bold-italic': pfBoldItalic,
  'pf--link': pfLink,
  'pf--h1': pfH1,
  'pf--h2': pfH2,
  'pf--h3': pfH3,
  'pf--h4': pfH3,
  'pf--h5': pfH3,
  'pf--h6': pfH3,
  'pf--inline-code': pfInlineCode,
  'pf--mention': pfMention,
};

export const pbullet = style({
  position: 'absolute',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  transform: 'translate(-50%, -50%)',
  fontSize: vars.typeBodyFontSize,
  fontFamily: vars.typeBodyFontFamily,
  lineHeight: 1,
  // color — applied via visual class in Prose.tsx
});

export const pquoteRail = style({
  position: 'absolute',
  top: 0,
  bottom: 0,
  width: '3px',
  // background and borderRadius — applied in Prose.tsx via visual class
});

// ── Visual (no measurement impact — color, background, decoration only) ───────

export const inlineCodeChip = style({
  borderRadius: '4px',
  background: vars.codeInlineBg,
});

/** Fallback for unknown mentionKind values. */
export const mentionChip = style({
  borderRadius: vars.radiusSm,
  background: vars.mentionChipBg,
  color: vars.mentionChipFg,
  boxShadow: `0 0 0 1px color-mix(in srgb, ${vars.fg} 10%, transparent)`,
});

export const mentionChipFile = style({
  borderRadius: vars.radiusSm,
  background: vars.mentionChipBg,
  color: vars.mentionChipFg,
  boxShadow: `0 0 0 1px color-mix(in srgb, ${vars.fg} 10%, transparent)`,
});

export const mentionChipIssue = style({
  borderRadius: vars.radiusSm,
  background: vars.mentionChipBg,
  color: vars.mentionChipFg,
  boxShadow: `0 0 0 1px color-mix(in srgb, ${vars.fg} 10%, transparent)`,
});

export const mentionChipSymbol = style({
  borderRadius: vars.radiusSm,
  background: vars.mentionChipBg,
  color: vars.mentionChipFg,
  boxShadow: `0 0 0 1px color-mix(in srgb, ${vars.fg} 10%, transparent)`,
});

export const mentionChipCustom = style({
  borderRadius: vars.radiusSm,
  background: vars.mentionCustomBg,
  color: vars.mentionCustomFg,
  boxShadow: `0 0 0 1px color-mix(in srgb, ${vars.fg} 10%, transparent)`,
});

/** Lookup from mentionKind to its visual class. Falls back to mentionChip. */
export const mentionChipByKind: Record<string, string> = {
  file: mentionChipFile,
  issue: mentionChipIssue,
  symbol: mentionChipSymbol,
  custom: mentionChipCustom,
};

export const mentionPlain = style({
  borderRadius: vars.radiusFull,
  background: vars.mentionBg,
  color: vars.mentionFg,
});

/** Slash-command chip — reuses the generic mention chip tint. */
export const commandChip = style({
  borderRadius: vars.radiusSm,
  background: vars.mentionCustomBg,
  color: vars.mentionCustomFg,
});

export const linkFragment = style({
  color: vars.link,
  textDecoration: 'underline',
  textDecorationThickness: '1px',
  textUnderlineOffset: '0.14em',
  cursor: 'pointer',
});

export const bulletColor = style({ color: vars.fgMuted });

export const quoteRailBar = style({
  background: vars.border,
  borderRadius: vars.radiusFull,
});
