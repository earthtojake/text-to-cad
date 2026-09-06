/**
 * Solarized Light theme — Ethan Schoonover's Solarized palette, light polarity.
 *
 * Solarized's defining trait is its *tinted* neutrals: a warm cream paper
 * (base3 #fdf6e3, OKLCH H≈90) that cools toward teal-gray body text
 * (base00/base01, H≈220). A single generated neutral hue cannot express that
 * warm-bg / cool-text split, so the neutral scale is supplied explicitly using
 * the canonical Solarized base tones. The surface generator derives the
 * background tint from neutral step 1, so this is what restores the warm paper.
 *
 * Accent + hue scales stay generated from authentic Solarized hex seeds (the
 * generator extracts hue and infers each scale's chroma peak), keeping them
 * accessible-by-construction while matching Solarized's accent colors.
 *
 * Canonical Solarized OKLCH reference (light backgrounds are warm H≈90):
 *   base3  #fdf6e3 L.974 C.026 H90   base2  #eee8d5 L.931 C.026 H92
 *   base1  #93a1a1 L.698 C.016 H197  base0  #839496 L.654 C.020 H205
 *   base00 #657b83 L.568 C.029 H222  base01 #586e75 L.523 C.028 H219
 *   base02 #073642 L.309 C.052 H220  base03 #002b36 L.267 C.049 H220
 *   blue #268bd2 H245  green #859900 H119  red #dc322f H27
 *   yellow #b58900 H86  orange #cb4b16 H40  violet #6c71c4 H279
 */

import { defineTheme } from '../core/index';

export const solarizedLightTheme = defineTheme({
  id: 'solarized-light',
  label: 'Solarized Light',
  polarity: 'light',

  // Signature Solarized blue accent (hue + chroma peak inferred from hex)
  accent: '#268bd2',

  hues: {
    green: '#859900',
    red: '#dc322f',
    amber: '#b58900',
    blue: '#268bd2',
    orange: '#cb4b16',
    purple: '#6c71c4',
  },

  // Authentic Solarized neutral ramp (light → dark): warm cream paper at the
  // top, cooling toward teal-gray text. Drives both the neutral scale and the
  // surface tint.
  scales: {
    neutral: [
      '#fdf6e3', // 1  base3   — page background (warm cream)
      '#f7f0dd', // 2  subtle background
      '#eee8d5', // 3  base2   — component background
      '#e7e0cb', // 4  hover
      '#ddd6bf', // 5  active / selected
      '#ccc6ad', // 6  subtle border
      '#b6b39c', // 7  ui border
      '#93a1a1', // 8  base1   — strong border / disabled text
      '#839496', // 9  base0   — solid fill
      '#657b83', // 10 base00  — hovered solid
      '#586e75', // 11 base01  — body text
      '#073642', // 12 base02  — high-contrast text
    ],
  },

  // APCA bg anchor for generated accent/hue text steps (matches base3)
  background: { lightness: 0.974 },

  // Solarized's surfaces top out at base3 (#fdf6e3, L≈0.974) — there is no
  // "whiter than paper" tone. The default light ladder pushes paper/elevated to
  // L≈0.993 (near-white), which gamut-clamps the warm chroma away. Pin the
  // ladder to authentic Solarized lightness so the cream tint survives.
  surfaceLightness: {
    sunken: 0.915, //               below base2 — recessed wells
    base: 0.945,
    'base-emphasis': 0.962,
    elevated: 0.974, //             base3 — cream panels
    'elevated-emphasis': 0.955,
    paper: 0.974, //                base3 — primary content background
  },

  gamut: 'p3',

  // Amber sits at a gamut cusp in light polarity (vivid yellow lives at high L).
  tweaks: {
    amber: {
      darkForeground: true,
      steps: {
        9: { l: +0.03 },
        10: { l: +0.02 },
        11: { l: -0.02 },
      },
    },
  },

  syntax: { generate: true },
});
