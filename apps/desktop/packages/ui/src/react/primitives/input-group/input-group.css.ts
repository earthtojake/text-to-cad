import { globalStyle, style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import { svgContainer, svgDefaultSize } from '@styles/effects/svg-helpers.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const inputGroup = recipe({
  base: {
    position: 'relative',
    display: 'flex',
    height: '2rem',
    width: '100%',
    minWidth: 0,
    alignItems: 'center',
    borderRadius: tokenVars.radiusMd,
    outline: 'none',
    selectors: {
      // block-end addon -> column layout
      '&:has(>[data-align="block-end"])': { height: 'auto', flexDirection: 'column' },
      '&:has(>[data-align="block-start"])': { height: 'auto', flexDirection: 'column' },
      // textarea child -> auto height
      '&:has(>textarea)': { height: 'auto' },
      // disabled state
      '&[data-disabled="true"]': { opacity: 0.5 },
    },
  },

  variants: {
    variant: {
      /**
       * default — standalone input group with border, shadow, and focus ring.
       * Use for form fields outside of popup containers.
       */
      default: {
        border: `1px solid ${vars.border}`,
        boxShadow: '0 1px 2px 0 rgba(0,0,0,0.05)',
        transition: 'color 150ms, box-shadow 150ms',
        selectors: {
          '&:has([data-slot="input-group-control"]:focus-visible)': {
            borderColor: vars.borderPrimary,
            boxShadow: `0 0 0 3px color-mix(in srgb, ${vars.borderPrimary} 30%, transparent)`,
          },
          '&:has([data-slot][aria-invalid="true"])': {
            borderColor: vars.borderDestructive,
            boxShadow: `0 0 0 3px color-mix(in srgb, ${vars.borderDestructive} 20%, transparent)`,
          },
        },
      },

      /**
       * embedded — for use inside a popup container (e.g. ComboboxInput inside ComboboxContent).
       * Strips the border to a bottom-only divider, removes the shadow and focus ring since
       * the surrounding popup provides visual containment.
       */
      embedded: {
        margin: 0,
        height: '2rem',
        borderTop: 'none',
        borderLeft: 'none',
        borderRight: 'none',
        borderBottom: `1px solid ${vars.border}`,
        borderRadius: 0,
        backgroundColor: 'transparent',
        boxShadow: 'none',
        width: 'auto',
        selectors: {
          '&:focus-within': { borderColor: 'inherit', boxShadow: 'none' },
        },
      },
    },
  },

  defaultVariants: {
    variant: 'default',
  },
});

// input padding adjustments when block addons are present (targeting child inputs)
globalStyle(`${inputGroup.classNames.base}:has(>[data-align="block-end"]) > input`, {
  paddingTop: '0.75rem',
});
globalStyle(`${inputGroup.classNames.base}:has(>[data-align="block-start"]) > input`, {
  paddingBottom: '0.75rem',
});
// inline addon input padding
globalStyle(`${inputGroup.classNames.base}:has(>[data-align="inline-end"]) > input`, {
  paddingRight: '0.375rem',
});
globalStyle(`${inputGroup.classNames.base}:has(>[data-align="inline-start"]) > input`, {
  paddingLeft: '0.375rem',
});

const inputGroupAddonBase = style([
  svgDefaultSize,
  {
    display: 'flex',
    height: 'auto',
    cursor: 'text',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    paddingTop: '0.375rem',
    paddingBottom: '0.375rem',
    fontSize: tokenVars.textSm,
    fontWeight: 400,
    color: vars.foregroundMuted,
    userSelect: 'none',
    selectors: {
      '[data-slot="input-group"][data-disabled="true"] &': { opacity: 0.5 },
    },
  },
]);
globalStyle(`${inputGroupAddonBase} > kbd`, { borderRadius: `calc(${tokenVars.radiusMd} - 5px)` });

export const inputGroupAddon = recipe({
  base: inputGroupAddonBase,
  variants: {
    align: {
      'inline-start': {
        order: -1,
        paddingLeft: '0.5rem',
        selectors: {
          '&:has(>button)': { marginLeft: '-0.25rem' },
          '&:has(>kbd)': { marginLeft: '-0.15rem' },
        },
      },
      'inline-end': {
        order: 1,
        paddingRight: '0.5rem',
        selectors: {
          '&:has(>button)': { marginRight: '-0.25rem' },
          '&:has(>kbd)': { marginRight: '-0.15rem' },
        },
      },
      'block-start': {
        order: -1,
        width: '100%',
        justifyContent: 'flex-start',
        paddingLeft: '0.625rem',
        paddingRight: '0.625rem',
        paddingTop: '0.5rem',
      },
      'block-end': {
        order: 1,
        width: '100%',
        justifyContent: 'flex-start',
        paddingLeft: '0.625rem',
        paddingRight: '0.625rem',
        paddingBottom: '0.5rem',
      },
    },
  },
  defaultVariants: {
    align: 'inline-start',
  },
});

export const inputGroupButton = style({
  borderRadius: `calc(${tokenVars.radiusMd} - 5px)`,
  boxShadow: 'none',
});

export const inputGroupText = style([
  svgContainer,
  svgDefaultSize,
  {
    display: 'flex',
    alignItems: 'center',
    gap: '0.5rem',
    fontSize: tokenVars.textSm,
    color: vars.foregroundMuted,
  },
]);

export const inputGroupControl = style({
  flex: 1,
  borderRadius: 0,
});

export const inputGroupTextareaControl = style({
  flex: 1,
  resize: 'none',
  borderRadius: 0,
  border: 0,
  backgroundColor: 'transparent',
  paddingTop: '0.5rem',
  paddingBottom: '0.5rem',
  boxShadow: 'none',
  selectors: {
    '&:focus-visible': { boxShadow: 'none' },
    '&[aria-invalid="true"]': { boxShadow: 'none' },
  },
});
