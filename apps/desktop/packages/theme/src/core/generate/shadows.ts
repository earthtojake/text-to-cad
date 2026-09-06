import { nsName } from '../contract/namespace';
import type { Polarity, Ramp, ShadowName } from '../contract/roles';

const SHADOW_ALPHA: Record<Polarity, Record<ShadowName, readonly number[]>> = {
  light: {
    sm: [10, 6],
    md: [12, 8],
    lg: [14, 10],
    overlay: [18, 12],
  },
  dark: {
    sm: [24, 14],
    md: [30, 18],
    lg: [36, 22],
    overlay: [44, 28],
  },
};

function shadowColor(color: string, alpha: number): string {
  return `color-mix(in srgb, ${color} ${alpha}%, transparent)`;
}

export function generateShadowVars(neutralRamp: Ramp, polarity: Polarity): Record<string, string> {
  const base = polarity === 'light' ? neutralRamp.steps[11] : neutralRamp.steps[0];
  const alpha = SHADOW_ALPHA[polarity];

  return {
    [nsName('shadow-sm')]: `0 1px 2px ${shadowColor(base, alpha.sm[0])}, 0 1px 1px ${shadowColor(
      base,
      alpha.sm[1]
    )}`,
    [nsName('shadow-md')]: `0 8px 24px ${shadowColor(base, alpha.md[0])}, 0 2px 8px ${shadowColor(
      base,
      alpha.md[1]
    )}`,
    [nsName('shadow-lg')]: `0 16px 48px ${shadowColor(base, alpha.lg[0])}, 0 4px 16px ${shadowColor(
      base,
      alpha.lg[1]
    )}`,
    [nsName('shadow-overlay')]: `0 24px 80px ${shadowColor(
      base,
      alpha.overlay[0]
    )}, 0 8px 32px ${shadowColor(base, alpha.overlay[1])}`,
  };
}
