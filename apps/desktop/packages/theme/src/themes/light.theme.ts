/**
 * Light theme — the default emdash light palette.
 *
 * Tuned to stay visually close to the current Radix-sourced emlight palette:
 *   - Neutral: pure gray (hue 0, very low chroma)
 *   - Accent: deeper jade/teal family (hue ~162)
 *   - Hue scales: green, red, amber, blue, orange, purple
 *   - Background lightness anchored to the current neutral.1 OKLCH L (~0.991)
 */

import { defineTheme } from '../core/index';

export const lightTheme = defineTheme({
  id: 'light',
  label: 'Light',
  polarity: 'light',

  accent: { hue: 162, chroma: 0.15 },
  neutral: { hue: 0, chroma: 0.002 },

  hues: {
    green: 147,
    red: 23,
    amber: 81,
    blue: 252,
    orange: 55,
    purple: 305,
  },

  contrast: 'normal',
  chroma: 1.15,
  background: { lightness: 0.991 },
  gamut: 'p3',

  // Amber sits at a gamut cusp: vivid yellow/amber lives at high L. This is a
  // property of the hue, so the tweak is keyed to the `amber` scale itself.
  // Use dark foreground on the solid step and nudge step lightness slightly.
  tweaks: {
    amber: {
      darkForeground: true,
      steps: {
        9: { l: +0.03 },
        10: { l: +0.02 },
        11: { l: -0.02 },
      },
    },
    accent: {
      steps: {
        9: { l: -0.08 },
        10: { l: -0.06 },
        11: { l: -0.04 },
      },
    },
  },

  syntax: { generate: true },
});
