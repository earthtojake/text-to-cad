import { nsName } from './contract/namespace';

export type DensityId = 'comfortable' | 'compact';

type SpaceTokenName =
  | 'space-0'
  | 'space-0-5'
  | 'space-1'
  | 'space-1-5'
  | 'space-2'
  | 'space-2-5'
  | 'space-3'
  | 'space-3-5'
  | 'space-4'
  | 'space-5'
  | 'space-6'
  | 'space-7'
  | 'space-8'
  | 'space-10'
  | 'space-12';

type RadiusTokenName =
  | 'radius'
  | 'radius-xs'
  | 'radius-sm'
  | 'radius-md'
  | 'radius-lg'
  | 'radius-xl'
  | 'radius-2xl'
  | 'radius-full';

type DensityTokenName = SpaceTokenName | RadiusTokenName;

export interface DensityInput {
  id: DensityId;
  label: string;
  spaceScale?: number;
  radiusScale?: number;
  overrides?: Partial<Record<DensityTokenName, string>>;
}

export interface ResolvedDensity {
  id: DensityId;
  label: string;
  selector: string;
  cssVars: Record<string, string>;
}

const BASE_SPACE: Record<SpaceTokenName, number> = {
  'space-0': 0,
  'space-0-5': 2,
  'space-1': 4,
  'space-1-5': 6,
  'space-2': 8,
  'space-2-5': 10,
  'space-3': 12,
  'space-3-5': 14,
  'space-4': 16,
  'space-5': 20,
  'space-6': 24,
  'space-7': 28,
  'space-8': 32,
  'space-10': 40,
  'space-12': 48,
};

const BASE_RADIUS: Record<RadiusTokenName, string> = {
  radius: '0.5rem',
  'radius-xs': '0.25rem',
  'radius-sm': '0.375rem',
  'radius-md': '0.5rem',
  'radius-lg': '0.625rem',
  'radius-xl': '0.875rem',
  'radius-2xl': '1.25rem',
  'radius-full': '9999px',
};

const scalableRadiusNames = Object.keys(BASE_RADIUS).filter(
  (name) => name !== 'radius-full'
) as Exclude<RadiusTokenName, 'radius-full'>[];

function px(value: number): string {
  if (value === 0) return '0';
  return `${Number(value.toFixed(3))}px`;
}

function remToPx(value: string): number {
  return Number(value.replace('rem', '')) * 16;
}

export function defineDensity(input: DensityInput): ResolvedDensity {
  const { id, label, spaceScale = 1, radiusScale = 1, overrides = {} } = input;
  const cssVars: Record<string, string> = {};

  for (const [name, value] of Object.entries(BASE_SPACE) as [SpaceTokenName, number][]) {
    cssVars[nsName(name)] = overrides[name] ?? px(value * spaceScale);
  }

  for (const name of scalableRadiusNames) {
    cssVars[nsName(name)] =
      overrides[name] ??
      (radiusScale === 1 ? BASE_RADIUS[name] : px(remToPx(BASE_RADIUS[name]) * radiusScale));
  }
  cssVars[nsName('radius-full')] = overrides['radius-full'] ?? BASE_RADIUS['radius-full'];

  return {
    id,
    label,
    selector: `.density-${id}`,
    cssVars,
  };
}
