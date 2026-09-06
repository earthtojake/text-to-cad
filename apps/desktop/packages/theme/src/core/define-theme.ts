/**
 * define-theme.ts
 *
 * The public API for creating a theme. Call defineTheme() to produce a
 * fully resolved ResolvedTheme from a compact set of inputs.
 *
 * Supports three palette authoring paths:
 *   1. Generated  — hue seeds + APCA curve (default; accessible by construction)
 *   2. Explicit   — supply all 12 steps directly (artisanal / imported palettes)
 *   3. Hybrid     — some scales generated, some explicit (e.g. branded accent)
 */

import { SCALE_NAMES } from './contract/roles';
import type {
  HueScaleName,
  Polarity,
  Ramp,
  ScaleName,
  Scales,
  Surfaces,
  SurfaceScopeName,
  SyntaxRole,
} from './contract/roles';
import { fillGaps } from './generate/fill-gaps';
import { generateRamp, generateNeutralRamp } from './generate/ramp';
import type { ScaleTweaks } from './generate/ramp';
import { resolveCssVars } from './generate/resolve';
import { generateShadowVars } from './generate/shadows';
import { generateSurfaces } from './generate/surfaces';
import { generateSyntaxVars } from './generate/syntax';
import type { SyntaxThemeInput } from './generate/syntax';

// ── ThemeInput ────────────────────────────────────────────────────────────────

export type HueSeed = number | string;

type ExplicitScaleInput = string[] | { steps: string[]; contrast?: string };

export interface ThemeInput {
  /** Unique identifier used as the CSS class name suffix: .em<id>. */
  id: string;
  /** Human-readable display name for UI pickers. */
  label: string;
  /** Polarity determines APCA target direction and L-curve orientation. */
  polarity: Polarity;

  // ── Palette hue seeds ──────────────────────────────────────────────────────
  /** Accent hue: the primary (swappable) brand color. Angle (0–360) or CSS/hex string. */
  accent: HueSeed | { hue: number; chroma?: number };
  /** Neutral: gray family used for backgrounds, borders, text. */
  neutral?: { hue?: number; chroma?: number };
  /**
   * Hue centers for the named color scales (green, red, amber, …).
   * Each is a hue angle (0–360) or a CSS/hex color to extract the hue from.
   * Missing entries fall back to the built-in Radix-derived defaults.
   * Semantic meaning (success, danger, merged, …) is assigned in
   * semantic-template.ts, not here.
   */
  hues?: Partial<Record<HueScaleName, HueSeed>>;

  // ── Curve character ────────────────────────────────────────────────────────
  /** Scale APCA targets globally. >1 = higher contrast (high-contrast mode). */
  contrast?: 'normal' | 'high' | number;
  /** Scale chroma globally. 1 = full, 0 = achromatic/monochrome. */
  chroma?: number;
  /** OKLCH L of the background (step 1). Low values = OLED/dark. */
  background?: { lightness?: number };
  /**
   * Per-scope OKLCH L overrides for the surface elevation ladder. Each entry
   * replaces the shared default in SURFACE_L (contract/targets.ts) for this
   * theme only; missing scopes fall back to the polarity default. Use this for
   * imported palettes whose surface lightness intent diverges from the default
   * ladder (e.g. Solarized's cream paper at base3 rather than near-white).
   * Tint (hue/chroma) still comes from the neutral ramp's step 1.
   */
  surfaceLightness?: Partial<Record<SurfaceScopeName, number>>;

  // ── Generation tuning ─────────────────────────────────────────────────────
  /**
   * Per-scale generation tweaks: bounded Δ adjustments to individual steps.
   * Used for gamut-cusp hues (yellow, amber) where the contrast curve
   * produces sub-optimal aesthetics.
   */
  tweaks?: Partial<Record<ScaleName, ScaleTweaks>>;

  /** Output color space for generated CSS strings. */
  gamut?: 'p3' | 'srgb';

  // ── Explicit scales escape hatch ──────────────────────────────────────────
  /**
   * Supply exact color values for one or more scales.
   * Provide 12 strings for a full scale, or fewer to fill gaps by interpolation.
   * Takes precedence over generated values for the same scale.
   */
  scales?: Partial<Record<ScaleName, ExplicitScaleInput>>;

  // ── Syntax highlighting ───────────────────────────────────────────────────
  /**
   * How to produce the syntax (code block) theme.
   *   { generate: true }         — generate from palette (default)
   *   { vscodeTheme: <json> }    — use an existing VSCode theme JSON directly
   *   "github-dark"              — bundled Shiki theme name (passthrough)
   *   Partial role overrides can be supplied alongside { generate: true }.
   */
  syntax?: SyntaxThemeInput & { roleOverrides?: Partial<Record<SyntaxRole, string>> };
}

// ── ResolvedTheme ─────────────────────────────────────────────────────────────

export interface ResolvedTheme {
  id: string;
  label: string;
  polarity: Polarity;
  /** CSS selector for this theme, e.g. ".emlight" or ".emdark". */
  selector: string;
  scales: Scales;
  surfaces: Surfaces;
  /**
   * Fully resolved CSS custom property map. Includes palette vars
   * (--neutral-1..12 etc.), surface vars, semantic vars, and syntax
   * token vars (--syntax-<role>, --syntax-editor-*).
   */
  cssVars: Record<string, string>;
}

// ── Built-in hue defaults (OKLCH hue angles, Radix-derived) ───────────────────

const DEFAULT_HUES: Record<HueScaleName, number> = {
  green: 147, // green / grass family
  red: 23, // red / tomato family
  amber: 81, // amber / yellow family (gamut-cusp hue)
  blue: 252, // blue family
  orange: 55, // orange family (between red and amber)
  purple: 305, // purple / plum / violet family
};

// ── Resolve contrast multiplier ───────────────────────────────────────────────

function resolveContrast(c: ThemeInput['contrast']): number {
  if (c === undefined || c === 'normal') return 1.0;
  if (c === 'high') return 1.25;
  return c;
}

// ── Resolve a single scale ────────────────────────────────────────────────────

function resolveScale(
  name: ScaleName,
  input: ThemeInput,
  explicitInput: ExplicitScaleInput | undefined
): Ramp {
  // Explicit takes precedence
  if (explicitInput != null) return fillGaps(explicitInput);

  const { polarity, chroma = 1.0, gamut = 'p3', tweaks } = input;
  const contrastMult = resolveContrast(input.contrast);
  const bgL = input.background?.lightness;
  const scaleTweaks = tweaks?.[name];

  const rampOpts = {
    polarity,
    chroma,
    contrast: contrastMult,
    bgLightness: bgL,
    gamut,
    tweaks: scaleTweaks,
  };

  if (name === 'neutral') {
    const n = input.neutral ?? {};
    return generateNeutralRamp({
      ...rampOpts,
      hue: n.hue ?? 0,
      neutralChroma: n.chroma,
    });
  }

  if (name === 'accent') {
    const acc = input.accent;
    const seed: HueSeed = typeof acc === 'object' && 'hue' in acc ? acc.hue : (acc as HueSeed);
    const accChromaPeak = typeof acc === 'object' && 'chroma' in acc ? acc.chroma : undefined;
    return generateRamp(seed, {
      ...rampOpts,
      tweaks: { ...scaleTweaks, ...(accChromaPeak != null ? { chromaPeak: accChromaPeak } : {}) },
    });
  }

  // Hue-named scales (green, red, amber, blue, orange, purple)
  const hue = input.hues?.[name as HueScaleName] ?? DEFAULT_HUES[name as HueScaleName] ?? 0;
  return generateRamp(hue, rampOpts);
}

// ── defineTheme ───────────────────────────────────────────────────────────────

/**
 * Produce a fully-resolved theme from a compact ThemeInput.
 * All colors are generated; the semantic template is applied; the syntax
 * theme is built. The result is ready for CSS emission by build.ts.
 */
export function defineTheme(input: ThemeInput): ResolvedTheme {
  const { id, label, polarity } = input;
  const selector = `.em${id}`;

  // 1. Resolve all scales
  const scales: Scales = {} as Scales;
  for (const name of SCALE_NAMES) {
    const explicit = input.scales?.[name];
    scales[name] = resolveScale(name, input, explicit);
  }

  // 2. Generate surfaces from the neutral ramp
  const surfaces = generateSurfaces(scales.neutral, polarity, input.surfaceLightness);

  // 3. Resolve CSS vars from the semantic template (done in resolve.ts, called here)
  const cssVars = resolveCssVars(scales, surfaces, polarity);

  // 4. Generate elevation shadow vars (--shadow-*)
  Object.assign(cssVars, generateShadowVars(scales.neutral, polarity));

  // 5. Generate syntax token vars (--syntax-<role>, --syntax-editor-*)
  const syntaxInput: SyntaxThemeInput = input.syntax ?? { generate: true };
  Object.assign(cssVars, generateSyntaxVars(scales, polarity, syntaxInput));

  return { id, label, polarity, selector, scales, surfaces, cssVars };
}
