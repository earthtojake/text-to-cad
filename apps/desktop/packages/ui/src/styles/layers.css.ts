/**
 * layers.css.ts — CSS @layer order declaration.
 *
 * Establishes cascade precedence for the @emdash/ui styling system.
 * Later layers win; import this file before any other VE stylesheet so the
 * declaration appears first in the compiled bundle.
 *
 * Precedence (lower → higher priority):
 *   reset < tokens < base < recipes < utilities
 *
 * - reset     mini-preflight / box-model normalization
 * - tokens    CSS custom properties (palette ramps, semantic aliases)
 * - base      global element defaults (body bg/fg, scrollbars, selection)
 * - recipes   component variant classes (VE recipe() output)
 * - utilities atomic helpers (sx() sprinkles, layout utils)
 *
 * The utilities layer sits highest so sx({ padding: '4' }) always overrides
 * a recipe base value — deterministic merge without tailwind-merge.
 */

import { globalLayer } from '@vanilla-extract/css';

export const resetLayer = globalLayer('reset');
export const tokensLayer = globalLayer('tokens');
export const baseLayer = globalLayer('base');
export const recipesLayer = globalLayer('recipes');
export const utilitiesLayer = globalLayer('utilities');
