import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const row = recipe({
  base: {
    display: 'flex',
    flexDirection: 'column',
    width: '100%',
    borderBottom: `1px solid ${vars.border}`,
    transition: 'background-color 100ms, color 100ms',
  },
  variants: {
    interactive: {
      true: {
        cursor: 'pointer',
        borderRadius: tokenVars.radiusMd,
        selectors: {
          '&:hover': { backgroundColor: vars.surfaceHover },
        },
      },
    },
    selected: {
      true: {
        borderRadius: tokenVars.radiusMd,
        backgroundColor: vars.surfaceSelected,
        selectors: {
          '&:hover': { backgroundColor: vars.surfaceSelected },
        },
      },
    },
    isLast: {
      true: { borderBottom: 'none' },
    },
    divider: {
      default: {},
      subtle: { borderBottomColor: vars.borderSubtle },
    },
  },
  defaultVariants: {
    interactive: false,
    selected: false,
    isLast: false,
    divider: 'default',
  },
});

export type RowVariants = NonNullable<RecipeVariants<typeof row>>;

/** Inner content padding for a standard Row. */
export const rowInner = style({
  display: 'flex',
  position: 'relative',
  alignItems: 'flex-start',
  gap: '0.75rem',
  padding: '0.75rem',
});

/**
 * SectionHeader — label + optional count, used by the Agents view
 * "Recommended (4)" / "All agents (12)" pattern.
 */
export const sectionHeader = style({
  display: 'flex',
  alignItems: 'center',
  gap: '0.375rem',
  paddingLeft: '0.75rem',
  paddingRight: '0.75rem',
  paddingTop: '0.5rem',
  paddingBottom: '0.25rem',
});

export const sectionHeaderLabel = style({
  fontSize: tokenVars.textTiny,
  fontWeight: 400,
  letterSpacing: '1.5px',
  textTransform: 'uppercase',
  color: vars.foregroundMuted,
});

export const sectionHeaderCount = style({
  fontSize: tokenVars.textXs,
  color: vars.foregroundMuted,
});
