/**
 * Generation constants: APCA target curves, elevation positions, and state ΔL.
 *
 * APCA Lc values are signed:
 *   light mode: text is darker than bg → negative Lc (colorjs contrastAPCA convention)
 *   dark mode:  text is lighter than bg → positive Lc
 *
 * Target curves are calibrated from the current Radix Color P3 neutral + jade
 * scales so generated ramps stay visually close to the existing palette:
 *
 *   Light neutral measured:  0, 0, 0, -11, -16, -21, -28, -39, -64, -69, -83, -104
 *   Dark  neutral measured:  0,  0,  0,  0,  0,  0, 12, 22, 28, 34, 63, 95
 *
 * Steps 1–3 are near-background and intentionally have Lc ≈ 0 (fills, not text).
 * Steps 11–12 anchor the text contrast targets (~60 / ~95 Lc).
 */

import type { Polarity, SurfaceScopeName } from './roles';

/**
 * Chroma curve: relative chroma multiplier per step (0..1 scale applied to chromaPeak).
 * Peaks at step 9 (solid fill); falls toward steps 1–3 (backgrounds) and 12 (text).
 * Calibrated so that neutral (chroma≈0) and vivid accents both read naturally.
 */
export const CHROMA_CURVE: readonly number[] = [
  0.05, // 1  — near-zero chroma (background)
  0.08, // 2
  0.14, // 3
  0.22, // 4
  0.34, // 5
  0.5, // 6
  0.68, // 7
  0.82, // 8
  1.0, // 9  — solid, full chroma peak
  0.96, // 10
  0.72, // 11 — text (slightly reduced for readability)
  0.45, // 12 — high-contrast text (further reduced)
];

/**
 * OKLab L shift applied to derive hover and selected state layers from a surface base.
 * Positive = lighter (dark mode convention); direction is inverted per polarity in generate/surfaces.ts.
 */
export const STATE_LAYER_DELTA = {
  hover: 0.04,
  selected: 0.08,
} as const;

/**
 * Absolute OKLCH L values for each surface level per polarity.
 *
 * Dark mode: elevation gets lighter at every step (monotonic, sunken darkest).
 *
 * Light mode: sunken is darkest, base is a mid gray, and `elevated` is near-white.
 * Emphasis is relative to its canvas: on the gray `base` it lightens
 * (base → base-emphasis, toward white). On the near-white `elevated` a card
 * reads as a subtle gray panel — slightly darker than `elevated` but never
 * darker than `base`. So light mode is intentionally non-monotonic by name.
 *
 * Surface roles (not part of the ladder):
 *   paper — primary content/tab background. White-ish in light (matches
 *   `elevated`), flat with `base` in dark. Light/dark are deliberately
 *   decoupled, which is why it lives outside SURFACE_LEVELS.
 *
 * Tune these values in Storybook after running theme:build.
 */
export const SURFACE_L: Record<Polarity, Record<SurfaceScopeName, number>> = {
  light: {
    sunken: 0.95,
    base: 0.972,
    'base-emphasis': 0.982,
    elevated: 0.993,
    'elevated-emphasis': 0.973,
    paper: 0.993,
  },
  dark: {
    sunken: 0.185,
    base: 0.215,
    'base-emphasis': 0.235,
    elevated: 0.265,
    'elevated-emphasis': 0.305,
    paper: 0.215,
  },
};

/**
 * Minimum APCA |Lc| for syntax token colors vs the code background.
 * Comment tokens get a looser target — intentionally lower contrast.
 */
export const SYNTAX_MIN_APCA: Record<string, number> = {
  comment: 30,
  default: 45,
};
