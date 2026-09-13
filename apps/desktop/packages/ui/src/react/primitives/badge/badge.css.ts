import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { svgContainer, svgSmSize } from '@styles/effects/svg-helpers.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const badge = recipe({
  base: [
    svgContainer,
    svgSmSize,
    {
      display: 'inline-flex',
      alignItems: 'center',
      justifyContent: 'center',
      width: 'fit-content',
      height: '1.125rem',
      flexShrink: 0,
      gap: '0.25rem',
      overflow: 'hidden',
      padding: '0 0.375rem',
      borderRadius: tokenVars.radiusXs,
      border: '1px solid transparent',
      fontSize: tokenVars.textMicro,
      fontWeight: 500,
      whiteSpace: 'nowrap',
      transition: 'color 150ms, background-color 150ms, border-color 150ms',
      selectors: {
        '&:focus-visible': {
          outline: 'none',
          borderColor: vars.borderPrimary,
          boxShadow: `0 0 0 3px color-mix(in srgb, ${vars.borderPrimary} 30%, transparent)`,
        },
      },
    },
  ],

  variants: {
    // Tone owns `color`; the variant derives its background/border from
    // currentColor so every tone × variant combination stays consistent.
    variant: {
      soft: {
        backgroundColor: 'color-mix(in srgb, currentColor 10%, transparent)',
      },
      outline: {
        backgroundColor: 'transparent',
        borderColor: 'color-mix(in srgb, currentColor 35%, transparent)',
      },
    },
    tone: {
      neutral: { color: vars.foregroundMuted },
      success: { color: vars.foregroundSuccess },
      warning: { color: vars.foregroundWarning },
      error: { color: vars.foregroundError },
      info: { color: vars.foregroundInfo },
    },
  },

  compoundVariants: [
    // Neutral outline reads as a quiet chip: full foreground text, hairline border.
    {
      variants: { variant: 'outline', tone: 'neutral' },
      style: { color: vars.foreground, borderColor: vars.border },
    },
  ],

  defaultVariants: {
    variant: 'soft',
    tone: 'neutral',
  },
});

export type BadgeVariants = NonNullable<RecipeVariants<typeof badge>>;
