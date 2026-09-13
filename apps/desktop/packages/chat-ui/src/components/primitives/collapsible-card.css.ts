import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';
import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

// ── Runtime geometry contract ─────────────────────────────────────────────────

export type CollapsibleCardStyleVars = {
  height: number;
};

export const collapsibleCardVars = createVariableThemeContract<CollapsibleCardStyleVars>({
  height: null,
});

// ── Card shell ────────────────────────────────────────────────────────────────

export const collapsibleCard = style({
  border: `1px solid ${vars.border}`,
  borderRadius: vars.radiusLg,
  overflow: 'hidden',
  boxSizing: 'border-box',
  height: collapsibleCardVars.height,
});
