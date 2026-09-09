import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { labelBase } from '../label/label.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const field = recipe({
  base: {
    display: 'flex',
    gap: '0.375rem',
    width: '100%',
  },
  variants: {
    orientation: {
      vertical: {
        flexDirection: 'column',
      },
      horizontal: {
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '1rem',
      },
    },
  },
  defaultVariants: {
    orientation: 'vertical',
  },
});

export type FieldVariants = NonNullable<RecipeVariants<typeof field>>;

// Label + description stacked, used in horizontal mode to occupy the left side.
export const fieldContent = style({
  display: 'flex',
  flexDirection: 'column',
  flex: 1,
  gap: '0.25rem',
  minWidth: 0,
});

// Constrains the control on the right side of a horizontal field row.
// Prevents inputs/selects from filling unlimited width; callers override via className.
// display:flex + justify-content:flex-end right-aligns narrow controls (e.g. Switch).
// marginLeft:auto pushes the slot to the right edge even when FieldContent is absent.
export const fieldControlSlot = style({
  display: 'flex',
  justifyContent: 'flex-end',
  alignItems: 'center',
  marginLeft: 'auto',
  flexShrink: 0,
  maxWidth: '12rem',
  width: '100%',
});

// Label typography is owned by the standalone Label primitive; Field.Label
// composes the same base so the two never drift.
export const fieldLabel = style([labelBase]);

export const fieldDescription = style({
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
  lineHeight: 1.5,
});

export const fieldError = style({
  fontSize: tokenVars.textSm,
  color: vars.foregroundDestructive,
});

// A semantic grouping of related fields (renders a <fieldset>).
export const fieldSet = style({
  display: 'flex',
  flexDirection: 'column',
  gap: '1.5rem',
  minWidth: 0,
  margin: 0,
  padding: 0,
  border: 0,
});

export const fieldLegend = recipe({
  base: {
    marginBottom: '0.75rem',
    padding: 0,
    fontWeight: 500,
    color: vars.foreground,
  },
  variants: {
    variant: {
      legend: { fontSize: tokenVars.textBase },
      label: { fontSize: tokenVars.textSm },
    },
  },
  defaultVariants: { variant: 'legend' },
});

export type FieldLegendVariants = NonNullable<RecipeVariants<typeof fieldLegend>>;

// Vertical stack of Field rows with consistent spacing.
export const fieldGroup = style({
  display: 'flex',
  flexDirection: 'column',
  width: '100%',
  gap: '1rem',
});
