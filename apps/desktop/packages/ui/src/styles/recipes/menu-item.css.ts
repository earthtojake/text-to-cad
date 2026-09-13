/**
 * menuItemBase — shared structural recipe for dropdown/combobox/select list items.
 *
 * Encapsulates the layout, spacing, and typography that is identical across
 * DropdownMenu, Select, Combobox, and ComboboxPopup item rows. Interaction
 * states (hover, focus, highlighted, selected, checked) are component-specific
 * and should be composed on top via `style([menuItemBase({ ... }), { selectors: ... }])`.
 *
 * Variants:
 *   trailingIndicator — adds paddingRight: 2rem to leave room for a check/radio indicator
 *   fullWidth         — sets width: 100% (combobox and select items span the full popup width)
 *   inset             — shifts paddingLeft to 2rem (for inset label alignment)
 *   muted             — sets color to foregroundMuted (checkbox/radio items start de-emphasised)
 */

import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { svgContainer, svgDefaultSize } from '@styles/effects/svg-helpers.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const menuItemBase = recipe({
  base: [
    svgContainer,
    svgDefaultSize,
    {
      position: 'relative',
      display: 'flex',
      minHeight: '1.75rem',
      cursor: 'default',
      alignItems: 'center',
      gap: '0.5rem',
      borderRadius: tokenVars.radiusSm,
      paddingTop: '0.25rem',
      paddingBottom: '0.25rem',
      paddingLeft: '0.5rem',
      paddingRight: '0.5rem',
      fontSize: tokenVars.textSm,
      outline: 'none',
      userSelect: 'none',
      transition: 'background-color 100ms, color 100ms',
    },
  ],

  variants: {
    trailingIndicator: {
      true: { paddingRight: '2rem' },
    },
    fullWidth: {
      true: { width: '100%' },
    },
    inset: {
      true: { paddingLeft: '2rem' },
    },
    muted: {
      true: { color: vars.foregroundMuted },
    },
  },

  defaultVariants: {
    trailingIndicator: false,
    fullWidth: false,
    inset: false,
    muted: false,
  },
});

export type MenuItemBaseVariants = RecipeVariants<typeof menuItemBase>;
