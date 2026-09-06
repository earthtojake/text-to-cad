import '@styles/layers.css';
import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const statusIcon = recipe({
  base: {
    '@layer': {
      recipes: {
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        borderRadius: tokenVars.radiusMd,
        flexShrink: 0,
      },
    },
  },
  variants: {
    severity: {
      success: {
        '@layer': {
          recipes: {
            backgroundColor: vars.backgroundSuccess,
            color: vars.foregroundSuccess,
          },
        },
      },
      error: {
        '@layer': {
          recipes: {
            backgroundColor: vars.backgroundError,
            color: vars.foregroundError,
          },
        },
      },
      warning: {
        '@layer': {
          recipes: {
            backgroundColor: vars.backgroundWarning,
            color: vars.foregroundWarning,
          },
        },
      },
      info: {
        '@layer': {
          recipes: {
            backgroundColor: vars.backgroundInfo,
            color: vars.foregroundInfo,
          },
        },
      },
      neutral: {
        '@layer': {
          recipes: {
            backgroundColor: `color-mix(in srgb, ${vars.foregroundMuted} 12%, transparent)`,
            color: vars.foregroundMuted,
          },
        },
      },
    },
    size: {
      sm: {
        '@layer': {
          recipes: {
            width: '1.25rem',
            height: '1.25rem',
          },
        },
      },
      md: {
        '@layer': {
          recipes: {
            width: '1.5rem',
            height: '1.5rem',
          },
        },
      },
      lg: {
        '@layer': {
          recipes: {
            width: '2.25rem',
            height: '2.25rem',
          },
        },
      },
    },
  },
  defaultVariants: {
    severity: 'neutral',
    size: 'md',
  },
});

export type StatusIconVariants = NonNullable<RecipeVariants<typeof statusIcon>>;

export const icon = recipe({
  base: {
    '@layer': {
      recipes: {
        display: 'block',
        color: 'currentColor',
      },
    },
  },
  variants: {
    size: {
      sm: {
        '@layer': {
          recipes: {
            width: '0.75rem',
            height: '0.75rem',
          },
        },
      },
      md: {
        '@layer': {
          recipes: {
            width: '0.875rem',
            height: '0.875rem',
          },
        },
      },
      lg: {
        '@layer': {
          recipes: {
            width: '1.25rem',
            height: '1.25rem',
          },
        },
      },
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export type StatusIconIconVariants = NonNullable<RecipeVariants<typeof icon>>;
