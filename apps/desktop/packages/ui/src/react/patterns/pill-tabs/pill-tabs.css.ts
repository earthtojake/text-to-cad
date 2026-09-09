import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import { svgContainer, svgSmSize } from '@styles/effects/svg-helpers.css';
import { sx } from '@styles/utilities/sprinkles.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

const motion = {
  transitionDuration: '200ms',
  transitionTimingFunction: 'ease-out',
  '@media': {
    '(prefers-reduced-motion: reduce)': {
      transitionDuration: '0ms',
    },
  },
} as const;

export const list = style({
  '@layer': {
    recipes: {
      display: 'flex',
      width: '100%',
      alignItems: 'stretch',
      gap: '0.5rem',
    },
  },
});

export const slot = recipe({
  base: {
    '@layer': {
      recipes: {
        display: 'flex',
        minWidth: 0,
        transitionProperty: 'flex-grow, flex-basis',
        ...motion,
      },
    },
  },
  variants: {
    compact: {
      false: {
        '@layer': {
          recipes: {
            flexBasis: 0,
            flexGrow: 1,
            flexShrink: 1,
          },
        },
      },
      true: {
        '@layer': {
          recipes: {
            flexBasis: '6rem',
            flexGrow: 0,
            flexShrink: 0,
          },
        },
      },
    },
  },
  defaultVariants: {
    compact: false,
  },
});

export const tab = style([
  sx({ px: '5', py: '2' }),
  {
    '@layer': {
      recipes: {
        display: 'inline-flex',
        width: '100%',
        minWidth: 0,
        alignItems: 'center',
        justifyContent: 'center',
        border: `1px solid ${vars.border}`,
        borderRadius: tokenVars.radiusLg,
        backgroundColor: vars.surfaceElevated,
        color: vars.foregroundMuted,
        font: 'inherit',
        cursor: 'pointer',
        transition: 'background-color 150ms, border-color 150ms, color 150ms',
        selectors: {
          '&:hover:not([data-disabled]):not([aria-disabled="true"])': {
            backgroundColor: vars.surfaceElevatedHover,
          },
          '&[data-selected], &[aria-selected="true"]': {
            borderColor: vars.borderPrimary,
            backgroundColor: vars.surfaceElevatedSelected,
            color: vars.foreground,
          },
          '&:disabled, &[data-disabled], &[aria-disabled="true"]': {
            cursor: 'not-allowed',
            opacity: 0.5,
          },
          '&:focus-visible': {
            outline: 'none',
            borderColor: vars.borderPrimary,
            boxShadow: `0 0 0 3px color-mix(in srgb, ${vars.borderPrimary} 30%, transparent)`,
          },
        },
      },
    },
  },
]);

export const content = style({
  '@layer': {
    recipes: {
      display: 'flex',
      width: '100%',
      minWidth: 0,
      alignItems: 'center',
      justifyContent: 'center',
    },
  },
});

export const icon = style([
  svgContainer,
  svgSmSize,
  {
    '@layer': {
      recipes: {
        display: 'inline-flex',
        flexShrink: 0,
        alignItems: 'center',
        justifyContent: 'center',
      },
    },
  },
]);

export const label = recipe({
  base: {
    '@layer': {
      recipes: {
        minWidth: 0,
        overflow: 'hidden',
        fontSize: tokenVars.textXs,
        lineHeight: 1.25,
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        transitionProperty: 'max-width, margin-left, opacity',
        ...motion,
      },
    },
  },
  variants: {
    hidden: {
      false: {
        '@layer': {
          recipes: {
            maxWidth: '16rem',
            marginLeft: '0.5rem',
            opacity: 1,
          },
        },
      },
      true: {
        '@layer': {
          recipes: {
            maxWidth: 0,
            marginLeft: 0,
            opacity: 0,
          },
        },
      },
    },
  },
  defaultVariants: {
    hidden: false,
  },
});
