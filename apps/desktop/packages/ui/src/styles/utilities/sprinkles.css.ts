// Side-effect imports — pulls VE modules into the build graph so their
// globalStyle output lands in dist/style.css.
import '../../theme/tokens.css';
import '../surfaces.css';
/**
 * sprinkles.css.ts — atomic CSS utilities for @emdash/ui.
 *
 * Built on the VE theme contract from contract/contract.css.ts so every
 * color/surface reference emits a typed var(--*) that automatically adapts to
 * the active .em<id> theme class and .surface-* cascade scope.
 *
 * Non-color design tokens use tokenVars. Spacing/radius values are generated
 * by @emdash/theme density classes; typography and motion values remain static
 * :root vars emitted by tokens.css.ts.
 *
 * Usage:
 *   import { sx } from '@emdash/ui/styles/sprinkles';
 *   <div className={sx({ display: 'flex', background: 'surface', padding: '3' })} />
 */
import { createSprinkles, defineProperties } from '@vanilla-extract/sprinkles';
import { tokenVars } from '../../theme/tokens.css';
import { vars } from '@theme/core/contract/contract.css';

// ── Layout ────────────────────────────────────────────────────────────────────

const layoutProps = defineProperties({
  properties: {
    display: ['flex', 'grid', 'block', 'inline', 'inline-block', 'inline-flex', 'none'],
    flexDirection: ['row', 'row-reverse', 'column', 'column-reverse'],
    alignItems: ['stretch', 'flex-start', 'center', 'flex-end', 'baseline'],
    alignSelf: ['auto', 'stretch', 'flex-start', 'center', 'flex-end'],
    justifyContent: ['stretch', 'flex-start', 'center', 'flex-end', 'space-between'],
    justifySelf: ['auto', 'stretch', 'flex-start', 'center', 'flex-end'],
    flexWrap: ['nowrap', 'wrap'],
    flex: { '1': '1 1 0%', none: 'none', auto: '1 1 auto' },
    flexShrink: { 0: 0, 1: 1 },
    flexGrow: { 0: 0, 1: 1 },
    position: ['static', 'relative', 'absolute', 'sticky', 'fixed'],
    overflow: ['visible', 'hidden', 'auto', 'scroll'],
    overflowX: ['visible', 'hidden', 'auto'],
    overflowY: ['visible', 'hidden', 'auto', 'scroll'],
    width: {
      full: '100%',
      auto: 'auto',
      '0': '0',
    },
    height: {
      full: '100%',
      auto: 'auto',
      '0': '0',
    },
    minWidth: {
      '0': '0',
      full: '100%',
    },
    minHeight: {
      '0': '0',
      full: '100%',
    },
    maxWidth: {
      full: '100%',
      none: 'none',
    },
    maxHeight: {
      full: '100%',
      none: 'none',
    },
    inset: { '0': '0' },
    top: { '0': '0', auto: 'auto' },
    right: { '0': '0', auto: 'auto' },
    bottom: { '0': '0', auto: 'auto' },
    left: { '0': '0', auto: 'auto' },
    zIndex: { '0': 0, '10': 10, '20': 20, '30': 30, '50': 50 },
    pointerEvents: ['none', 'auto', 'all'],
    visibility: ['visible', 'hidden'],
    shrink: { '0': 0, '1': 1 },
  },
});

// ── Spacing ───────────────────────────────────────────────────────────────────

const SPACE = {
  '0': tokenVars.space0,
  '0.5': tokenVars.space0_5,
  '1': tokenVars.space1,
  '1.5': tokenVars.space1_5,
  '2': tokenVars.space2,
  '2.5': tokenVars.space2_5,
  '3': tokenVars.space3,
  '3.5': tokenVars.space3_5,
  '4': tokenVars.space4,
  '5': tokenVars.space5,
  '6': tokenVars.space6,
  '7': tokenVars.space7,
  '8': tokenVars.space8,
  '10': tokenVars.space10,
  '12': tokenVars.space12,
} as const;

const spacingProps = defineProperties({
  properties: {
    padding: SPACE,
    paddingTop: SPACE,
    paddingBottom: SPACE,
    paddingLeft: SPACE,
    paddingRight: SPACE,
    gap: SPACE,
    columnGap: SPACE,
    rowGap: SPACE,
    marginTop: SPACE,
    marginBottom: SPACE,
    marginLeft: SPACE,
    marginRight: SPACE,
  },
  shorthands: {
    px: ['paddingLeft', 'paddingRight'],
    py: ['paddingTop', 'paddingBottom'],
    p: ['padding'],
    mx: ['marginLeft', 'marginRight'],
    my: ['marginTop', 'marginBottom'],
  },
});

// ── Typography ─────────────────────────────────────────────────────────────────

const typographyProps = defineProperties({
  properties: {
    fontSize: {
      micro: tokenVars.textMicro,
      tiny: tokenVars.textTiny,
      xs: tokenVars.textXs,
      sm: tokenVars.textSm,
      base: tokenVars.textBase,
      lg: tokenVars.textLg,
      xl: tokenVars.textXl,
    },
    fontWeight: {
      normal: tokenVars.fontWeightNormal,
    },
    lineHeight: {
      none: 1,
      tight: 1.25,
      snug: 1.375,
      normal: 1.5,
    },
    whiteSpace: ['nowrap', 'pre', 'pre-wrap', 'normal'],
    textOverflow: ['ellipsis', 'clip'],
    wordBreak: ['break-all', 'break-word', 'normal'],
    userSelect: ['none', 'auto', 'all', 'text'],
    cursor: ['default', 'pointer', 'text', 'not-allowed', 'auto'],
    textDecoration: ['none', 'underline', 'line-through'],
    textAlign: ['left', 'center', 'right'],
    fontStyle: ['normal', 'italic'],
    textTransform: ['none', 'uppercase', 'lowercase', 'capitalize'],
    fontFamily: {
      sans: tokenVars.fontSans,
      mono: tokenVars.fontMono,
    },
  },
});

// ── Colors ────────────────────────────────────────────────────────────────────

const colorProps = defineProperties({
  properties: {
    color: {
      inherit: 'inherit',
      current: 'currentColor',
      // Foreground scale
      foreground: vars.foreground,
      foregroundBody: vars.foregroundBody,
      foregroundMuted: vars.foregroundMuted,
      foregroundPassive: vars.foregroundPassive,
      foregroundInverse: vars.foregroundInverse,
      // Semantic foregrounds
      foregroundDestructive: vars.foregroundDestructive,
      foregroundDestructiveMuted: vars.foregroundDestructiveMuted,
      foregroundNeutral: vars.foregroundNeutral,
      // Diff / VCS
      foregroundDiffAdded: vars.foregroundDiffAdded,
      foregroundDiffModified: vars.foregroundDiffModified,
      foregroundDiffDeleted: vars.foregroundDiffDeleted,
      foregroundConflict: vars.foregroundConflict,
      foregroundMerged: vars.foregroundMerged,
      // State sets
      foregroundSuccess: vars.foregroundSuccess,
      foregroundError: vars.foregroundError,
      foregroundWarning: vars.foregroundWarning,
      foregroundInfo: vars.foregroundInfo,
      // Status
      statusInProgress: vars.statusInProgress,
      statusInReview: vars.statusInReview,
      statusDone: vars.statusDone,
      statusTodo: vars.statusTodo,
      statusCancelled: vars.statusCancelled,
      // Primary button
      primaryButtonForeground: vars.primaryButtonForeground,
      // Surface cascade — reads foreground from nearest .surface-* scope
      surfaceForeground: vars.surfaceForeground,
      // Surface status foregrounds
      surfaceDestructiveForeground: vars.surfaceDestructiveForeground,
      surfaceWarningForeground: vars.surfaceWarningForeground,
      surfaceInfoForeground: vars.surfaceInfoForeground,
    },
    background: {
      transparent: 'transparent',
      // Base backgrounds
      background: vars.background,
      background1: vars.background1,
      background2: vars.background2,
      background3: vars.background3,
      // Semantic backgrounds
      backgroundDestructive: vars.backgroundDestructive,
      backgroundDestructive1: vars.backgroundDestructive1,
      backgroundNeutral: vars.backgroundNeutral,
      backgroundSuccess: vars.backgroundSuccess,
      backgroundSuccessHover: vars.backgroundSuccessHover,
      backgroundError: vars.backgroundError,
      backgroundErrorHover: vars.backgroundErrorHover,
      backgroundWarning: vars.backgroundWarning,
      backgroundWarningHover: vars.backgroundWarningHover,
      backgroundInfo: vars.backgroundInfo,
      backgroundInfoHover: vars.backgroundInfoHover,
      // Primary button
      primaryButtonBackground: vars.primaryButtonBackground,
      primaryButtonBackgroundHover: vars.primaryButtonBackgroundHover,
      // ── Surface cascade — the core of the surface system ──────────────────
      // Generic: adapts to the nearest .surface-* ancestor class
      surface: vars.surface,
      surfaceHover: vars.surfaceHover,
      surfaceSelected: vars.surfaceSelected,
      surfaceEmphasis: vars.surfaceEmphasis,
      surfaceEmphasisHover: vars.surfaceEmphasisHover,
      surfaceEmphasisSelected: vars.surfaceEmphasisSelected,
      surfaceInput: vars.surfaceInput,
      // Direct elevation levels — target a specific level regardless of scope
      surfaceSunken: vars.surfaceSunken,
      surfaceSunkenHover: vars.surfaceSunkenHover,
      surfaceSunkenSelected: vars.surfaceSunkenSelected,
      surfaceBase: vars.surfaceBase,
      surfaceBaseHover: vars.surfaceBaseHover,
      surfaceBaseSelected: vars.surfaceBaseSelected,
      surfaceBaseEmphasis: vars.surfaceBaseEmphasis,
      surfaceBaseEmphasisHover: vars.surfaceBaseEmphasisHover,
      surfaceBaseEmphasisSelected: vars.surfaceBaseEmphasisSelected,
      surfaceElevated: vars.surfaceElevated,
      surfaceElevatedHover: vars.surfaceElevatedHover,
      surfaceElevatedSelected: vars.surfaceElevatedSelected,
      surfaceElevatedEmphasis: vars.surfaceElevatedEmphasis,
      surfaceElevatedEmphasisHover: vars.surfaceElevatedEmphasisHover,
      surfaceElevatedEmphasisSelected: vars.surfaceElevatedEmphasisSelected,
      surfacePaper: vars.surfacePaper,
      surfacePaperHover: vars.surfacePaperHover,
      surfacePaperSelected: vars.surfacePaperSelected,
      // Status surface rooms
      surfaceDestructive: vars.surfaceDestructive,
      surfaceDestructiveHover: vars.surfaceDestructiveHover,
      surfaceDestructiveSelected: vars.surfaceDestructiveSelected,
      surfaceWarning: vars.surfaceWarning,
      surfaceWarningHover: vars.surfaceWarningHover,
      surfaceWarningSelected: vars.surfaceWarningSelected,
      surfaceInfo: vars.surfaceInfo,
      surfaceInfoHover: vars.surfaceInfoHover,
      surfaceInfoSelected: vars.surfaceInfoSelected,
    },
    borderColor: {
      transparent: 'transparent',
      current: 'currentColor',
      border: vars.border,
      border1: vars.border1,
      border2: vars.border2,
      borderDestructive: vars.borderDestructive,
      borderPrimary: vars.borderPrimary,
      borderSuccess: vars.borderSuccess,
      borderError: vars.borderError,
      borderWarning: vars.borderWarning,
      borderInfo: vars.borderInfo,
      primaryButtonBorder: vars.primaryButtonBorder,
      // Surface-relative border (set by .surface-<status> scope classes)
      surfaceBorder: vars.surfaceBorder,
      surfaceDestructiveBorder: vars.surfaceDestructiveBorder,
      surfaceWarningBorder: vars.surfaceWarningBorder,
      surfaceInfoBorder: vars.surfaceInfoBorder,
    },
    outlineColor: {
      border: vars.border,
      borderPrimary: vars.borderPrimary,
      borderDestructive: vars.borderDestructive,
    },
  },
});

// ── Borders & Radius ──────────────────────────────────────────────────────────

const RADIUS = {
  '0': '0',
  xs: tokenVars.radiusXs,
  sm: tokenVars.radiusSm,
  md: tokenVars.radiusMd,
  lg: tokenVars.radiusLg,
  xl: tokenVars.radiusXl,
  '2xl': tokenVars.radius2xl,
  full: tokenVars.radiusFull,
} as const;

const borderProps = defineProperties({
  properties: {
    borderWidth: { '0': '0', '1': '1px', '2': '2px' },
    borderTopWidth: { '0': '0', '1': '1px', '2': '2px', '3': '3px' },
    borderBottomWidth: { '0': '0', '1': '1px', '2': '2px', '3': '3px' },
    borderLeftWidth: { '0': '0', '1': '1px', '2': '2px', '3': '3px' },
    borderRightWidth: { '0': '0', '1': '1px', '2': '2px', '3': '3px' },
    borderStyle: ['solid', 'dashed', 'dotted', 'none'],
    borderRadius: RADIUS,
    borderTopLeftRadius: RADIUS,
    borderTopRightRadius: RADIUS,
    borderBottomLeftRadius: RADIUS,
    borderBottomRightRadius: RADIUS,
    opacity: {
      '0': 0,
      '50': 0.5,
      '75': 0.75,
      '100': 1,
    },
    boxShadow: {
      none: 'none',
      sm: vars.shadowSm,
      md: vars.shadowMd,
      lg: vars.shadowLg,
      overlay: vars.shadowOverlay,
    },
  },
  shorthands: {
    rounded: ['borderRadius'],
    roundedTop: ['borderTopLeftRadius', 'borderTopRightRadius'],
    roundedBottom: ['borderBottomLeftRadius', 'borderBottomRightRadius'],
    roundedLeft: ['borderTopLeftRadius', 'borderBottomLeftRadius'],
    roundedRight: ['borderTopRightRadius', 'borderBottomRightRadius'],
  },
});

// ── Combined sprinkles function ───────────────────────────────────────────────

export const sx = createSprinkles(
  layoutProps,
  spacingProps,
  typographyProps,
  colorProps,
  borderProps
);

export type Sprinkles = Parameters<typeof sx>[0];
