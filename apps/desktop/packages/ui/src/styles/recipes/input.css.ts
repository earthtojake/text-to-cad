/**
 * inputVariants — Vanilla Extract recipe replacing the CVA inputVariants.
 * Used by Input, Textarea, and InputGroup control slots.
 *
 * Visual shell (border, background, focus ring, hover, invalid) is composed
 * from fieldShellBase so Select/Combobox triggers can share the same look.
 */

import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { fieldShellBase } from './field-shell.css';
import { tokenVars } from '@theme/tokens.css';

export const inputVariants = recipe({
  base: [
    fieldShellBase,
    {
      width: '100%',
      minWidth: 0,
      fontSize: tokenVars.textSm,
      colorScheme: 'light',
    },
  ],

  variants: {
    size: {
      base: {
        height: '2rem',
        paddingLeft: '0.625rem',
        paddingRight: '0.625rem',
        paddingTop: '0.25rem',
        paddingBottom: '0.25rem',
      },
      sm: {
        height: '1.75rem',
        paddingLeft: '0.5rem',
        paddingRight: '0.5rem',
        paddingTop: '0.125rem',
        paddingBottom: '0.125rem',
        fontSize: tokenVars.textSm,
      },
    },

    /**
     * bare — strips the standalone border, background, and focus ring so the input
     * can live inside a group container that provides those affordances.
     * Removes the need for !important overrides on the wrapping control slot.
     */
    bare: {
      true: {
        border: 0,
        backgroundColor: 'transparent',
        boxShadow: 'none',
        selectors: {
          '&:hover': { borderColor: 'inherit' },
          '&:focus-visible': { borderColor: 'inherit', boxShadow: 'none' },
          '&[aria-invalid="true"]': { borderColor: 'inherit', boxShadow: 'none' },
        },
      },
    },
  },

  defaultVariants: {
    size: 'base',
    bare: false,
  },
});

export type InputVariantProps = NonNullable<RecipeVariants<typeof inputVariants>>;
