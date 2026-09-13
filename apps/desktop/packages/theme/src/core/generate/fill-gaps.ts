/**
 * generate/fill-gaps.ts
 *
 * Converts partial or full explicit scale inputs (string[] or { steps, contrast })
 * into fully typed Ramp objects, filling missing steps via OKLCH interpolation.
 *
 * Used for the "explicit scales" escape hatch in defineTheme:
 *   scales: { neutral: ['#111', '#222', ..., '#eee'] }
 * or partial:
 *   scales: { accent: { steps: ['#1e40af', '#3b82f6', '#93c5fd'], contrast: '#fff' } }
 */

import Color from 'colorjs.io';
import type { Ramp } from '../contract/roles';
import { toP3String, pickContrastColor } from './color-format';

type ExplicitScaleInput = string[] | { steps: string[]; contrast?: string };

function parseInput(input: ExplicitScaleInput): { steps: string[]; contrast?: string } {
  if (Array.isArray(input)) return { steps: input };
  return input;
}

function pickContrastColorFromStep(solidStep: string): string {
  try {
    const c = new Color(solidStep);
    return pickContrastColor(c, undefined, 'srgb');
  } catch {
    return '#ffffff';
  }
}

/**
 * Fill a partial step array to 12 steps via OKLCH L interpolation.
 * If fewer than 2 anchors are provided, the color is replicated.
 * If exactly 12 are provided, returned as-is.
 */
function fillTo12(steps: string[]): string[] {
  if (steps.length === 12) return [...steps];
  if (steps.length === 0) throw new Error('fillGaps: at least one step is required');

  if (steps.length === 1) {
    return Array(12).fill(steps[0]) as string[];
  }

  // Parse all provided steps into OKLCH
  const parsedColors: Color[] = steps.map((s) => {
    try {
      return new Color(s).to('oklch');
    } catch {
      throw new Error(`fillGaps: cannot parse color "${s}"`);
    }
  });

  // Distribute the provided steps evenly across 12 positions
  const result: string[] = [];
  for (let i = 0; i < 12; i++) {
    const t = (i / 11) * (parsedColors.length - 1);
    const lo = Math.floor(t);
    const hi = Math.min(parsedColors.length - 1, lo + 1);
    const frac = t - lo;

    const cLo = parsedColors[lo];
    const cHi = parsedColors[hi];

    // Interpolate L, C in OKLCH (cylindrical — use shortest-path hue)
    const L = cLo.coords[0] + (cHi.coords[0] - cLo.coords[0]) * frac;
    const C = cLo.coords[1] + (cHi.coords[1] - cLo.coords[1]) * frac;

    // Hue interpolation: take shortest arc
    let dH = (cHi.coords[2] ?? 0) - (cLo.coords[2] ?? 0);
    if (dH > 180) dH -= 360;
    if (dH < -180) dH += 360;
    const H = (cLo.coords[2] ?? 0) + dH * frac;

    let color = new Color('oklch', [L, C, H]);
    if (!color.inGamut('p3')) {
      color = color.toGamut({ space: 'p3' }) as Color;
    }

    result.push(toP3String(color.to('p3')));
  }

  return result;
}

/**
 * Convert an explicit scale input into a full Ramp (12 steps + contrast).
 * Missing steps are filled by OKLCH interpolation between provided anchors.
 */
export function fillGaps(input: ExplicitScaleInput): Ramp {
  const { steps: rawSteps, contrast } = parseInput(input);
  const filledSteps = fillTo12(rawSteps);
  const solidStep = filledSteps[8]; // step 9 (0-indexed = 8)
  return {
    steps: filledSteps as unknown as Ramp['steps'],
    contrast: contrast ?? pickContrastColorFromStep(solidStep),
  };
}
