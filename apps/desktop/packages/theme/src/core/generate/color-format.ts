/**
 * generate/color-format.ts
 *
 * Shared color formatting and contrast utilities used across the generate/ modules.
 * Consolidates the duplicated toP3String / toSrgbString / pickContrastColor / resolveRef
 * that previously lived independently in ramp.ts, surfaces.ts, fill-gaps.ts, and syntax.ts.
 */

import Color from 'colorjs.io';
import type { Scales } from '../contract/roles';

const FORMAT_PRECISION = 4;

// ── Formatting ────────────────────────────────────────────────────────────────

export function toP3String(c: Color): string {
  const p3 = c.to('p3');
  const [r, g, b] = p3.coords.map((v) =>
    Math.max(0, Math.min(1, +Number(v).toFixed(FORMAT_PRECISION)))
  );
  return `color(display-p3 ${r} ${g} ${b})`;
}

export function toSrgbString(c: Color): string {
  const srgb = c.to('srgb');
  const [r, g, b] = srgb.coords.map((v) =>
    Math.max(0, Math.min(1, +Number(v).toFixed(FORMAT_PRECISION)))
  );
  return `rgb(${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)})`;
}

export function formatColor(c: Color, gamut: 'p3' | 'srgb'): string {
  return gamut === 'p3' ? toP3String(c) : toSrgbString(c);
}

// ── Contrast ──────────────────────────────────────────────────────────────────

/**
 * Auto-select white or dark text for use on a solid (step 9) background.
 * When darkForeground is true the dark color is always returned (for gamut-cusp
 * hues like amber where the solid step is inherently light).
 */
export function pickContrastColor(
  solidColor: Color,
  darkForeground: boolean | undefined,
  gamut: 'p3' | 'srgb'
): string {
  const darkText = gamut === 'p3' ? 'color(display-p3 0.125 0.125 0.125)' : '#1a1a1a';
  const lightText = gamut === 'p3' ? 'color(display-p3 1 1 1)' : '#ffffff';

  if (darkForeground) return darkText;

  const white = new Color('oklch', [1, 0, 0]);
  const black = new Color('oklch', [0.12, 0, 0]);
  const lcWhite = Math.abs(solidColor.contrastAPCA(white) as number);
  const lcBlack = Math.abs(solidColor.contrastAPCA(black) as number);
  return lcWhite >= lcBlack ? lightText : darkText;
}

// ── Ref resolution ────────────────────────────────────────────────────────────

/**
 * Resolve a palette ref like "neutral.11" or "accent.contrast" to a CSS color
 * string from the resolved scales map.
 */
export function resolveScaleRef(ref: string, scales: Scales): string {
  const [scaleName, stepOrContrast] = ref.split('.') as [keyof Scales, string];
  const scale = scales[scaleName];
  if (!scale) throw new Error(`resolveScaleRef: unknown scale "${scaleName}" in ref "${ref}"`);

  if (stepOrContrast === 'contrast') return scale.contrast;

  const stepNum = parseInt(stepOrContrast, 10);
  if (isNaN(stepNum) || stepNum < 1 || stepNum > 12) {
    throw new Error(`resolveScaleRef: invalid step "${stepOrContrast}" in ref "${ref}"`);
  }

  return scale.steps[stepNum - 1];
}

// ── CSS color to hex ──────────────────────────────────────────────────────────

export function colorToHex(cssColor: string): string {
  try {
    const c = new Color(cssColor);
    const srgb = c.to('srgb');
    const r = Math.round(Math.max(0, Math.min(1, srgb.coords[0])) * 255);
    const g = Math.round(Math.max(0, Math.min(1, srgb.coords[1])) * 255);
    const b = Math.round(Math.max(0, Math.min(1, srgb.coords[2])) * 255);
    return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('');
  } catch {
    return cssColor;
  }
}
