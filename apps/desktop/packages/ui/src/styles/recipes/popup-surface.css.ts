/**
 * popupSurface — shared base style for floating popup containers.
 *
 * Encapsulates the properties that are identical across DropdownMenu, Select,
 * Combobox, and ComboboxPopup content panels: animation entry/exit keyframes
 * keyed to [data-open]/[data-closed] and [data-side], the ring shadow formula,
 * and core visual properties.
 *
 * Each primitive extends this by composing it into their own `style()`:
 *   export const menuContent = style([popupSurface, { overflowY: 'auto', ... }]);
 *
 * Variants in sizing (minWidth, overflowY, anchor-width usage) and shadow depth
 * are applied at the composing level, not here.
 */

import { style } from '@vanilla-extract/css';
import {
  kfPopupIn,
  kfPopupOut,
  kfPopupInSlideFromTop,
  kfPopupInSlideFromBottom,
  kfPopupInSlideFromLeft,
  kfPopupInSlideFromRight,
} from '@styles/effects/animations.css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

const popupSurfaceBase = style({
  position: 'relative',
  zIndex: 50,
  transformOrigin: 'var(--transform-origin)',
  borderRadius: tokenVars.radiusMd,
  outline: 'none',
  selectors: {
    '&[data-open]': { animation: `${kfPopupIn} 100ms both` },
    '&[data-open][data-side="bottom"]': { animation: `${kfPopupInSlideFromTop} 100ms both` },
    '&[data-open][data-side="top"]': { animation: `${kfPopupInSlideFromBottom} 100ms both` },
    '&[data-open][data-side="right"]': { animation: `${kfPopupInSlideFromLeft} 100ms both` },
    '&[data-open][data-side="inline-end"]': { animation: `${kfPopupInSlideFromLeft} 100ms both` },
    '&[data-open][data-side="left"]': { animation: `${kfPopupInSlideFromRight} 100ms both` },
    '&[data-open][data-side="inline-start"]': {
      animation: `${kfPopupInSlideFromRight} 100ms both`,
    },
    '&[data-closed]': { animation: `${kfPopupOut} 100ms both` },
  },
});

export const popupSurface = style([
  popupSurfaceBase,
  {
    backgroundColor: vars.surface,
    color: vars.foreground,
  },
]);

/**
 * Inverted (neutral pill) tone for high-contrast popups such as tooltips —
 * same structure and animations as `popupSurface`, but painted with the
 * theme's inverted neutral slots.
 */
export const popupSurfaceInverted = style([
  popupSurfaceBase,
  {
    backgroundColor: vars.backgroundNeutral,
    color: vars.foregroundNeutral,
  },
]);

/**
 * Shadow tokens for popup containers.
 * - ringSm: subtle ring + gentle shadow (combobox, tooltips)
 * - ringMd: deeper shadow (dropdown menus, selects)
 */
export const popupShadowSm = style({
  boxShadow: `${vars.shadowSm}, 0 0 0 1px color-mix(in srgb, ${vars.foreground} 10%, transparent)`,
});

export const popupShadowMd = style({
  boxShadow: `${vars.shadowMd}, 0 0 0 1px color-mix(in srgb, ${vars.foreground} 10%, transparent)`,
});
