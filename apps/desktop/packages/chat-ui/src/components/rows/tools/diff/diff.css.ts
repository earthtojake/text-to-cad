import { globalStyle, style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import { textShimmer } from '@styles/effects.css';
import { vars } from '@styles/theme.css';
import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

// ── Runtime geometry contract ─────────────────────────────────────────────────

export type DiffStyleVars = {
  height: number;
  headerH: number;
};

export const diffCardVars = createVariableThemeContract<DiffStyleVars>({
  height: null,
  headerH: null,
});

export const diffRoot = style({ height: diffCardVars.height });

// ── DiffHeader ────────────────────────────────────────────────────────────────

export const diffHeader = recipe({
  base: {
    height: diffCardVars.headerH,
    border: `1px solid ${vars.border}`,
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    paddingLeft: '8px',
    paddingRight: '8px',
    cursor: 'pointer',
    fontSize: '0.75rem',
    transition: 'background 150ms',
    selectors: {
      '&:hover': { background: vars.bg3 },
    },
  },
  variants: {
    hasBody: {
      true: {
        borderTopLeftRadius: vars.radiusLg,
        borderTopRightRadius: vars.radiusLg,
        borderBottom: 'none',
      },
      false: {
        borderRadius: vars.radiusLg,
      },
    },
  },
});

export const diffFileName = style({
  color: vars.fgMuted,
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: vars.typeBodyFontSize,
});

export const diffAddsCount = style({
  color: vars.diffAdded,
  flexShrink: 0,
  fontSize: vars.typeBodyFontSize,
});
export const diffDelsCount = style({
  color: vars.diffDeleted,
  flexShrink: 0,
  fontSize: vars.typeBodyFontSize,
});
export const diffSpacer = style({ flex: '1 1 0%' });
export const diffStatusIcon = style({
  display: 'flex',
  flexShrink: 0,
});
export const diffPermissionIcon = style([
  diffStatusIcon,
  {
    color: vars.planActive,
  },
]);
export const diffErrorIcon = style([
  diffStatusIcon,
  {
    color: vars.fgError,
  },
]);

// ── DiffLines body ────────────────────────────────────────────────────────────

export const diffBodyCard = style({
  border: `1px solid ${vars.border}`,
  borderBottomLeftRadius: vars.radiusLg,
  borderBottomRightRadius: vars.radiusLg,
  overflow: 'hidden',
});

/** Per-row classes — keyed by DiffRow type. */
export const diffRowClasses = {
  add: style({
    display: 'flex',
    background: `color-mix(in srgb, ${vars.diffAdded} 10%, transparent)`,
    borderLeft: `3px solid ${vars.diffAdded}`,
  }),
  remove: style({
    display: 'flex',
    background: `color-mix(in srgb, ${vars.diffDeleted} 10%, transparent)`,
    borderLeft: `3px solid ${vars.diffDeleted}`,
  }),
  context: style({
    display: 'flex',
    borderLeft: '3px solid transparent',
  }),
} as const;

export const diffLineContent = style({
  color: vars.fg,
  flex: '1 1 0%',
  overflow: 'hidden',
  paddingLeft: '12px',
  paddingRight: '12px',
});

// ── Shiki line styles ─────────────────────────────────────────────────────────

export const pdiffBody = style({
  position: 'relative',
});

export const pdiffLine = style({
  whiteSpace: 'pre',
  fontSize: vars.typeCodeFontSize,
  fontWeight: vars.typeCodeFontWeight,
  fontFamily: vars.typeCodeFontFamily,
  // line-height is set via inline style in Diff.tsx (from theme.fonts.code.lineHeight)
  // so it cannot drift from the measured value via a CSS variable.
});

globalStyle(`${pdiffLine} span`, {
  color: 'var(--shiki-light)',
});

globalStyle(`.emdark ${pdiffLine} span`, {
  color: 'var(--shiki-dark)',
});

export { textShimmer };
