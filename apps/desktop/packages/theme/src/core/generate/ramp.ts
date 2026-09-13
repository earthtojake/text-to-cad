/**
 * generate/ramp.ts
 *
 * Generates a perceptually-coherent 12-step OKLCH color scale from a hue seed.
 *
 * Two-zone algorithm:
 *
 *   Zone A — Background zone (steps 1–6):
 *     APCA is unreliable for very-low-contrast colors (returns 0 for Lc < ~8).
 *     Instead, L is linearly interpolated in OKLab from the background anchor
 *     down to the APCA threshold boundary. This produces the subtle background
 *     tints (hover states, component surfaces, subtle borders).
 *
 *   Zone B — Text zone (steps 7–12):
 *     APCA Lc targets are achieved via binary search on L.
 *     These steps are intended for borders, interactive text, and solid fills.
 *
 * Chroma is applied independently via the CHROMA_CURVE, peaking at step 9.
 * Per-step tweaks (Δ L/C/H) are applied after zone interpolation.
 * Colors are clamped to the target gamut (p3 or srgb).
 * The contrast color for step 9 (solid) is auto-selected (white or black by APCA).
 *
 * APCA Lc polarity (colorjs.io convention):
 *   Light mode: text is darker than bg → negative Lc
 *   Dark mode:  text is lighter than bg → positive Lc
 */

import Color from 'colorjs.io';
import type { Polarity, Ramp, Step } from '../contract/roles';
import { CHROMA_CURVE } from '../contract/targets';
import { formatColor, pickContrastColor } from './color-format';

// ── Public types ──────────────────────────────────────────────────────────────

export type HueSeed = number | string;

export type StepTweak = {
  /** Additive OKLCH L delta (−0.15 .. +0.15 recommended). */
  l?: number;
  /** Additive chroma delta. */
  c?: number;
  /** Additive hue angle delta in degrees. */
  h?: number;
};

export type ScaleTweaks = {
  steps?: Partial<Record<Step, StepTweak>>;
  /**
   * Force the contrast color (text on step 9) to dark.
   * Required for gamut-cusp hues like yellow/amber whose solid step
   * is inherently light.
   */
  darkForeground?: boolean;
  /** Override the chroma peak for this scale. */
  chromaPeak?: number;
};

export type RampOptions = {
  polarity: Polarity;
  /** Global chroma multiplier (1.0 = full, 0 = achromatic/monochrome). */
  chroma?: number;
  /** Contrast multiplier applied to text-zone APCA targets (>1 = higher contrast). */
  contrast?: number;
  /** OKLCH L of the background anchor for APCA calculations. */
  bgLightness?: number;
  /** Output color space for generated CSS strings. */
  gamut?: 'p3' | 'srgb';
  tweaks?: ScaleTweaks;
};

// ── Constants ─────────────────────────────────────────────────────────────────

const DEFAULT_CHROMA_PEAK = 0.17;
const NEUTRAL_CHROMA_PEAK = 0.004;
const BINARY_SEARCH_ITERATIONS = 55;
const APCA_SOLVE_TOLERANCE = 0.5;

/**
 * APCA targets for the text zone (steps 7–12) per polarity.
 * These are achievable because they are well above the APCA threshold (~8 Lc).
 */
const TEXT_ZONE_APCA: Record<Polarity, readonly number[]> = {
  light: [-28, -40, -64, -69, -84, -104], // steps 7-12
  dark: [22, 32, 45, 52, 65, 92], // steps 7-12
};

/**
 * OKLab L endpoints for the background zone boundary (step 6's target L).
 * Step 1 is at bgL; step 6 linearly interpolates toward this boundary.
 *
 * Light: bg ≈ 0.97, bg zone ends ≈ 0.83 (subtle border territory)
 * Dark:  bg ≈ 0.18, bg zone ends ≈ 0.34 (just below APCA threshold)
 */
const BG_ZONE_END_L: Record<Polarity, number> = {
  light: 0.82,
  dark: 0.34,
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function extractHue(seed: HueSeed): number {
  if (typeof seed === 'number') return seed;
  try {
    const c = new Color(seed).to('oklch');
    const h = c.coords[2];
    return typeof h === 'number' && !Number.isNaN(h) ? h : 0;
  } catch {
    return 0;
  }
}

function inferChromaPeak(seed: HueSeed): number {
  if (typeof seed === 'string') {
    try {
      const c = new Color(seed).to('oklch');
      const ch = c.coords[1];
      if (typeof ch === 'number' && !Number.isNaN(ch) && ch > 0) {
        return Math.max(0.06, Math.min(0.35, ch));
      }
    } catch {
      // fall through
    }
  }
  return DEFAULT_CHROMA_PEAK;
}

/**
 * Binary-search OKLCH L until contrastAPCA ≈ targetLc.
 * Only called for text-zone steps where APCA is well above its threshold.
 *
 * Light: targetLc < 0 (text darker than bg → lower L = more negative).
 * Dark:  targetLc > 0 (text lighter than bg → higher L = more positive).
 */
function solveLForAPCA(
  hue: number,
  chroma: number,
  targetLc: number,
  bgColor: Color,
  polarity: Polarity
): number {
  let lo = 0.0;
  let hi = 1.0;

  for (let i = 0; i < BINARY_SEARCH_ITERATIONS; i++) {
    const mid = (lo + hi) / 2;
    const c = new Color('oklch', [mid, chroma, hue]);
    const lc = c.contrastAPCA(bgColor) as number;

    if (Math.abs(lc - targetLc) < APCA_SOLVE_TOLERANCE) break;

    if (polarity === 'light') {
      // targetLc < 0. Lower L = darker = more negative Lc.
      if (lc > targetLc) {
        hi = mid; // lc is less negative (lighter than needed) → reduce L
      } else {
        lo = mid; // lc is more negative (darker than needed) → increase L
      }
    } else {
      // targetLc > 0. Higher L = lighter = more positive Lc.
      if (lc < targetLc) {
        lo = mid; // not enough positive contrast → increase L
      } else {
        hi = mid; // too much positive contrast → decrease L
      }
    }
  }

  return (lo + hi) / 2;
}

function clampToGamut(c: Color, gamut: 'p3' | 'srgb'): Color {
  const space = gamut === 'p3' ? 'p3' : 'srgb';
  return c.inGamut(space) ? c : (c.toGamut({ space }) as Color);
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Generate a 12-step OKLCH color scale from a hue seed.
 *
 * seed: hue angle (0–360) or CSS/hex color string (hue is extracted).
 */
export function generateRamp(seed: HueSeed, opts: RampOptions): Ramp {
  const { polarity, chroma = 1.0, contrast = 1.0, gamut = 'p3' } = opts;
  const tweaks = opts.tweaks ?? {};

  const hue = extractHue(seed);
  const chromaPeak = tweaks.chromaPeak ?? inferChromaPeak(seed);
  const scaledChromaPeak = chromaPeak * chroma;

  const bgL = opts.bgLightness ?? (polarity === 'light' ? 0.991 : 0.178);

  // Background color for APCA text-zone calculations
  const bgChroma = scaledChromaPeak * 0.015; // very slight bg tint
  const bgColor = new Color('oklch', [bgL, bgChroma, hue]);

  const textZoneTargets = TEXT_ZONE_APCA[polarity].map((t) => t * contrast);
  const bgZoneEndL = BG_ZONE_END_L[polarity];

  const resultSteps: string[] = [];
  let solidColorRef: Color | null = null;

  for (let i = 0; i < 12; i++) {
    const step = (i + 1) as Step;
    const stepChroma = CHROMA_CURVE[i] * scaledChromaPeak;

    let L: number;

    if (i < 6) {
      // Background zone: linear L interpolation from bgL to bgZoneEndL
      // i=0 → t=0 (bgL), i=5 → t=5/5=1 (bgZoneEndL)
      const t = i / 5;
      L = bgL + (bgZoneEndL - bgL) * t;
    } else {
      // Text zone: APCA-solve (steps 7-12, i=6..11)
      const targetLc = textZoneTargets[i - 6];
      L = solveLForAPCA(hue, stepChroma, targetLc, bgColor, polarity);
    }

    // Apply per-step tweaks
    const tweak = tweaks.steps?.[step];
    const finalL = tweak?.l != null ? Math.max(0, Math.min(1, L + tweak.l)) : L;
    const finalC = Math.max(0, stepChroma + (tweak?.c ?? 0));
    const finalH = hue + (tweak?.h ?? 0);

    let color = new Color('oklch', [finalL, finalC, finalH]);
    color = clampToGamut(color, gamut);

    if (step === 9) solidColorRef = color.clone();

    resultSteps.push(formatColor(color, gamut));
  }

  const solidColor = solidColorRef ?? new Color('oklch', [0.5, scaledChromaPeak, hue]);
  const contrastColor = pickContrastColor(solidColor, tweaks.darkForeground, gamut);

  return {
    steps: resultSteps as unknown as Ramp['steps'],
    contrast: contrastColor,
    darkForeground: tweaks.darkForeground,
  };
}

/**
 * Generate a neutral (gray or warm-gray) scale.
 * hue: warmth angle (0 = pure gray, 60 = warm, 250 = cool blue-gray).
 */
export function generateNeutralRamp(
  opts: RampOptions & { hue?: number; neutralChroma?: number }
): Ramp {
  const { hue = 0, neutralChroma, ...rest } = opts;
  return generateRamp(hue, {
    ...rest,
    tweaks: {
      ...rest.tweaks,
      chromaPeak: neutralChroma ?? NEUTRAL_CHROMA_PEAK,
    },
  });
}
