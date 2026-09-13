/**
 * theme.css.ts — VE global theme contract + chat-ui default theme.
 *
 * CONTRACT (vars)
 *   createGlobalThemeContract defines the stable public CSS variable names
 *   (--chat-fg, --chat-type-body-font-size, --chat-font-sans, ...) that every
 *   .css.ts file and host override preset depend on.
 *
 * DEFAULT THEME (createGlobalTheme × 2)
 *   The two createGlobalTheme calls are the chat-ui built-in default theme.
 *   Typography metric and chip-pad values are derived from DEFAULT_CONFIG so
 *   this file and the runtime buildChatTheme share the same single source of truth.
 *   Color/radii/family literals are kept inline here (host can override them via
 *   class-selector rules without inline-style specificity issues).
 *   Specificity is zero (:where() selectors) so any host override wins
 *   regardless of stylesheet load order.
 *
 * HOST OVERRIDE (chat-theme.css)
 *   The optional chat-theme.css preset rebinds --chat-font-sans, colors and
 *   radii to the emdash design-system tokens (system sans on desktop). It
 *   inherits everything not explicitly overridden from this default theme.
 */

import { DEFAULT_CONFIG, toThemeVars } from '@core/config';
import { createGlobalTheme, createGlobalThemeContract } from '@vanilla-extract/css';

// ── Contract (stable public names) ────────────────────────────────────────────

// The second argument to createGlobalThemeContract is a mapFn that receives
// the leaf value and returns the CSS custom property name.
// We use the value itself as the name suffix so the TS key and CSS name are
// both visible: vars.fg compiles to var(--chat-fg).

export const vars = createGlobalThemeContract(
  {
    // ── Color palette ─────────────────────────────────────────────────────────
    fg: 'chat-fg',
    fgBody: 'chat-fg-body',
    fgMuted: 'chat-fg-muted',
    fgPassive: 'chat-fg-passive',
    bg: 'chat-bg',
    bg1: 'chat-bg-1',
    bg2: 'chat-bg-2',
    bg3: 'chat-bg-3',
    border: 'chat-border',

    // User message card surface
    userCardBg: 'chat-user-card-bg',
    userCardBorder: 'chat-user-card-border',
    userCardBorderHover: 'chat-user-card-border-hover',

    // Resolved context-mention pill — per-kind bg/fg vars
    mentionChipBg: 'chat-mention-chip-bg',
    mentionChipFg: 'chat-mention-chip-fg',
    mentionFileBg: 'chat-mention-file-bg',
    mentionFileFg: 'chat-mention-file-fg',
    mentionIssueBg: 'chat-mention-issue-bg',
    mentionIssueFg: 'chat-mention-issue-fg',
    mentionSymbolBg: 'chat-mention-symbol-bg',
    mentionSymbolFg: 'chat-mention-symbol-fg',
    mentionCustomBg: 'chat-mention-custom-bg',
    mentionCustomFg: 'chat-mention-custom-fg',

    // Diff surface
    diffAdded: 'chat-diff-added',
    diffDeleted: 'chat-diff-deleted',
    diffModified: 'chat-diff-modified',

    // Misc semantic
    fgError: 'chat-fg-error',
    link: 'chat-link',
    bubbleUser: 'chat-bubble-user',
    bubbleUserFg: 'chat-bubble-user-fg',
    mentionBg: 'chat-mention-bg',
    mentionFg: 'chat-mention-fg',
    codeBg: 'chat-code-bg',
    codeInlineBg: 'chat-code-inline-bg',
    tableHeaderBg: 'chat-table-header-bg',
    planDone: 'chat-plan-done',
    planActive: 'chat-plan-active',

    // ── Non-color design tokens ────────────────────────────────────────────────
    fontSans: 'chat-font-sans',
    fontMono: 'chat-font-mono',
    radiusSm: 'chat-radius-sm',
    radiusMd: 'chat-radius-md',
    radiusLg: 'chat-radius-lg',
    radiusXl: 'chat-radius-xl',
    radiusFull: 'chat-radius-full',

    // ── Private typography (--chat-type-*) ────────────────────────────────────
    // These names must NOT change — prose.css.ts / diff.css.ts reference them
    // and any rename breaks the measure === offsetHeight invariant.
    typeBodyFontFamily: 'chat-type-body-font-family',
    typeBodyFontSize: 'chat-type-body-font-size',
    typeBodyFontWeight: 'chat-type-body-font-weight',
    typeBodyLineHeight: 'chat-type-body-line-height',

    typeBodyBoldFontFamily: 'chat-type-body-bold-font-family',
    typeBodyBoldFontSize: 'chat-type-body-bold-font-size',
    typeBodyBoldFontWeight: 'chat-type-body-bold-font-weight',
    typeBodyBoldLineHeight: 'chat-type-body-bold-line-height',

    typeBodyItalicFontFamily: 'chat-type-body-italic-font-family',
    typeBodyItalicFontSize: 'chat-type-body-italic-font-size',
    typeBodyItalicFontWeight: 'chat-type-body-italic-font-weight',
    typeBodyItalicFontStyle: 'chat-type-body-italic-font-style',
    typeBodyItalicLineHeight: 'chat-type-body-italic-line-height',

    typeBodyLinkFontFamily: 'chat-type-body-link-font-family',
    typeBodyLinkFontSize: 'chat-type-body-link-font-size',
    typeBodyLinkFontWeight: 'chat-type-body-link-font-weight',
    typeBodyLinkLineHeight: 'chat-type-body-link-line-height',

    typeH1FontFamily: 'chat-type-h1-font-family',
    typeH1FontSize: 'chat-type-h1-font-size',
    typeH1FontWeight: 'chat-type-h1-font-weight',
    typeH1LineHeight: 'chat-type-h1-line-height',

    typeH2FontFamily: 'chat-type-h2-font-family',
    typeH2FontSize: 'chat-type-h2-font-size',
    typeH2FontWeight: 'chat-type-h2-font-weight',
    typeH2LineHeight: 'chat-type-h2-line-height',

    typeH3FontFamily: 'chat-type-h3-font-family',
    typeH3FontSize: 'chat-type-h3-font-size',
    typeH3FontWeight: 'chat-type-h3-font-weight',
    typeH3LineHeight: 'chat-type-h3-line-height',

    typeInlineCodeFontFamily: 'chat-type-inline-code-font-family',
    typeInlineCodeFontSize: 'chat-type-inline-code-font-size',
    typeInlineCodeFontWeight: 'chat-type-inline-code-font-weight',
    typeInlineCodeLineHeight: 'chat-type-inline-code-line-height',

    typeCodeFontFamily: 'chat-type-code-font-family',
    typeCodeFontSize: 'chat-type-code-font-size',
    typeCodeFontWeight: 'chat-type-code-font-weight',
    typeCodeLineHeight: 'chat-type-code-line-height',

    typeCodeLangFontFamily: 'chat-type-code-lang-font-family',
    typeCodeLangFontSize: 'chat-type-code-lang-font-size',
    typeCodeLangFontWeight: 'chat-type-code-lang-font-weight',
    typeCodeLangLineHeight: 'chat-type-code-lang-line-height',

    // Mention chip typography (size/weight emitted at runtime like all other roles).
    typeMentionFontFamily: 'chat-type-mention-font-family',
    typeMentionFontSize: 'chat-type-mention-font-size',
    typeMentionFontWeight: 'chat-type-mention-font-weight',

    // ── Chip padding (runtime-settable by ChatRoot) ────────────────────────────
    icPadX: 'chat-ic-pad-x',
    icPadY: 'chat-ic-pad-y',
    mentionPadX: 'chat-mention-pad-x',
    mentionPadY: 'chat-mention-pad-y',
  },
  (value) => `--${value}`
);

// ── Shared non-color tokens ────────────────────────────────────────────────────
//
// Typography metrics and chip padding derive from DEFAULT_CONFIG via toThemeVars
// (same source of truth as buildChatTheme) so build-time defaults and runtime
// inline-var emission can never drift from each other. Both createGlobalTheme
// blocks spread these; each block then only lists its own color palette.
//
// Font-family and radius tokens are static across themes, so they live here too.
// The vars contract keys match the ThemeVarKey union in config.ts exactly —
// TypeScript enforces this in ChatRoot via vars[k as ThemeVarKey] lookups.

const NON_COLOR_VARS = {
  fontSans: ['Inter Variable', 'sans-serif'].join(', '),
  fontMono: "'JetBrains Mono Variable', 'JetBrains Mono', Menlo, Monaco, monospace",
  radiusSm: '0.375rem',
  radiusMd: '0.5rem',
  radiusLg: '0.625rem',
  radiusXl: '0.875rem',
  radiusFull: '9999px',
  // Typography + chip padding — all derived from DEFAULT_CONFIG.
  ...toThemeVars(DEFAULT_CONFIG),
};

// ── Light theme ────────────────────────────────────────────────────────────────

createGlobalTheme(':where(:root), :where(.emlight)', vars, {
  fg: '#21201f',
  fgBody: 'color-mix(in srgb, #616060 40%, #21201f)',
  fgMuted: '#616060',
  fgPassive: '#8e8d8d',
  bg: '#fcfcfc',
  bg1: '#f1f0f0',
  bg2: '#e5e4e4',
  bg3: '#dadada',
  border: '#c5c4c4',
  userCardBg: '#f1f0f0',
  userCardBorder: '#c5c4c4',
  userCardBorderHover: '#b3b2b2',
  mentionChipBg: '#e7e6e6',
  mentionChipFg: '#21201f',
  mentionFileBg: '#e7e6e6',
  mentionFileFg: '#21201f',
  mentionIssueBg: '#dbeafe',
  mentionIssueFg: '#1d4ed8',
  mentionSymbolBg: '#ede9fe',
  mentionSymbolFg: '#6d28d9',
  mentionCustomBg: '#e7e6e6',
  mentionCustomFg: '#21201f',
  diffAdded: '#4f9f4f',
  diffDeleted: '#d56761',
  diffModified: '#c28c00',
  fgError: '#d56761',
  link: '#2263a4',
  bubbleUser: '#dadada',
  bubbleUserFg: '#21201f',
  mentionBg: '#dbeafe',
  mentionFg: '#1d4ed8',
  codeBg: '#fcfcfc',
  codeInlineBg: 'rgba(0, 0, 0, 0.06)',
  tableHeaderBg: '#f1f0f0',
  planDone: '#22c55e',
  planActive: '#f59e0b',
  ...NON_COLOR_VARS,
});

// ── Dark theme ─────────────────────────────────────────────────────────────────
// Only colors differ from light — typography and geometry are theme-independent.

createGlobalTheme(':where(.emdark)', vars, {
  fg: '#e9e8e9',
  fgBody: 'color-mix(in srgb, #b8b7b8 40%, #e9e8e9)',
  fgMuted: '#b8b7b8',
  fgPassive: '#929091',
  bg: '#111111',
  bg1: '#181818',
  bg2: '#202020',
  bg3: '#282727',
  border: '#373636',
  userCardBg: '#181818',
  userCardBorder: '#373636',
  userCardBorderHover: '#525050',
  mentionChipBg: '#2a2929',
  mentionChipFg: '#e6e6e6',
  mentionFileBg: '#2a2929',
  mentionFileFg: '#e6e6e6',
  mentionIssueBg: '#1a293a',
  mentionIssueFg: '#7cbcff',
  mentionSymbolBg: '#2a2440',
  mentionSymbolFg: '#c4b5fd',
  mentionCustomBg: '#2a2929',
  mentionCustomFg: '#e6e6e6',
  diffAdded: '#54a55a',
  diffDeleted: '#dc6b67',
  diffModified: '#ce981d',
  fgError: '#dc6b67',
  link: '#7cbcff',
  bubbleUser: '#282727',
  bubbleUserFg: '#e9e8e9',
  mentionBg: '#1a293a',
  mentionFg: '#7cbcff',
  codeBg: '#111111',
  codeInlineBg: 'rgba(255, 255, 255, 0.08)',
  tableHeaderBg: '#181818',
  planDone: '#4fcca8',
  planActive: '#dead52',
  ...NON_COLOR_VARS,
});
