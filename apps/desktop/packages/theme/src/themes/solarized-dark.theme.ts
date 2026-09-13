/**
 * Solarized Dark theme — Ethan Schoonover's Solarized palette, dark polarity.
 *
 * Solarized Dark is built on the cool teal base tones (base03 #002b36,
 * OKLCH H≈220) that lighten toward teal-gray text (base0/base1). As in the
 * light theme, the neutral scale is supplied explicitly from the canonical
 * Solarized base tones so the surface generator picks up the cool teal tint
 * from neutral step 1 (this is the "tint" the generated single-hue ramp lost).
 *
 * Accent + hue scales stay generated from authentic Solarized hex seeds.
 *
 * Canonical Solarized OKLCH reference (dark backgrounds are cool teal H≈220):
 *   base03 #002b36 L.267 C.049 H220  base02 #073642 L.309 C.052 H220
 *   base01 #586e75 L.523 C.028 H219  base00 #657b83 L.568 C.029 H222
 *   base0  #839496 L.654 C.020 H205  base1  #93a1a1 L.698 C.016 H197
 *   base2  #eee8d5 L.931 C.026 H92   base3  #fdf6e3 L.974 C.026 H90
 *   blue #268bd2 H245  green #859900 H119  red #dc322f H27
 *   yellow #b58900 H86  orange #cb4b16 H40  violet #6c71c4 H279
 */

import { defineTheme } from '../core/index';

export const solarizedDarkTheme = defineTheme({
  id: 'solarized-dark',
  label: 'Solarized Dark',
  polarity: 'dark',

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

  // Authentic Solarized neutral ramp (dark → light): cool teal base at the
  // bottom, lightening toward teal-gray text. Drives both the neutral scale and
  // the cool surface tint.
  scales: {
    neutral: [
      '#002b36', // 1  base03  — page background (cool teal)
      '#073642', // 2  base02  — subtle background
      '#0b3d49', // 3  component background
      '#0f4654', // 4  hover
      '#164f5d', // 5  active / selected
      '#2c5a64', // 6  subtle border
      '#475c63', // 7  ui border
      '#586e75', // 8  base01  — strong border / disabled text
      '#657b83', // 9  base00  — solid fill
      '#839496', // 10 base0   — hovered solid
      '#93a1a1', // 11 base1   — body text
      '#eee8d5', // 12 base2   — high-contrast text
    ],
  },

  // APCA bg anchor for generated accent/hue text steps (matches base03)
  background: { lightness: 0.267 },

  // Solarized Dark's canonical base is base03 (#002b36, L≈0.267), with base02
  // (#073642, L≈0.309) for raised panels — both lighter than the default dark
  // ladder's near-black base. Pin the ladder to those tones so the teal base is
  // authentic rather than crushed toward black.
  surfaceLightness: {
    sunken: 0.235,
    base: 0.267, //                 base03 — primary background
    'base-emphasis': 0.295,
    elevated: 0.309, //             base02 — raised panels
    'elevated-emphasis': 0.345,
    paper: 0.267, //                base03 — primary content background
  },

  gamut: 'p3',

  tweaks: {
    amber: {
      darkForeground: true,
      steps: {
        9: { l: +0.05 },
        10: { l: +0.04 },
        11: { l: -0.01 },
      },
    },
  },

  syntax: { generate: true },
});
