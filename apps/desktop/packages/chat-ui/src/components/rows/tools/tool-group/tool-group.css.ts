import { style } from '@vanilla-extract/css';
import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

// ── Runtime geometry contract ─────────────────────────────────────────────────

export type ToolGroupStyleVars = {
  height: number;
};

export const toolGroupCardVars = createVariableThemeContract<ToolGroupStyleVars>({
  height: null,
});

/**
 * Root container clipped to the measured composite height.
 * overflow:hidden ensures transient measure-vs-render desync degrades to
 * clipping rather than overflowing into the next row.
 */
export const toolGroupRoot = style({
  height: toolGroupCardVars.height,
  overflow: 'hidden',
});
