import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';
import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

// ── Runtime geometry contract ─────────────────────────────────────────────────

export type ResourceLinkStyleVars = { rowH: number };

export const resourceLinkVars = createVariableThemeContract<ResourceLinkStyleVars>({ rowH: null });

export const resourceLinkRoot = style({
  height: resourceLinkVars.rowH,
  display: 'flex',
  alignItems: 'stretch',
});

const rowBase = style({
  display: 'flex',
  alignItems: 'center',
  gap: '8px',
  fontSize: vars.typeBodyFontSize,
  height: '100%',
});

export const rowStatic = rowBase;

export const rowClickable = style([
  rowBase,
  {
    cursor: 'pointer',
    padding: '8px',
    borderRadius: vars.radiusLg,
    border: `1px solid ${vars.border}`,
    width: '100%',
    transition: 'background 150ms, color 150ms',
    selectors: {
      '&:hover': {
        background: vars.bg2,
        color: vars.fg,
      },
    },
  },
]);

export const iconWrap = style({ color: vars.fgMuted, flexShrink: 0 });
export const titleText = style({
  color: vars.fgBody,
  flexShrink: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});
export const pathText = style({
  color: vars.fgMuted,
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
  fontSize: '0.75rem',
});
export const sizeText = style({
  color: vars.fgMuted,
  flexShrink: 0,
  fontSize: '0.75rem',
  fontWeight: 400,
});
