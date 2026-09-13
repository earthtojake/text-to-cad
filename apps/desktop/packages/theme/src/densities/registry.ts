import { defineDensity } from '../core/define-density';

export const comfortableDensity = defineDensity({
  id: 'comfortable',
  label: 'Comfortable',
  radiusScale: 0,
});

export const compactDensity = defineDensity({
  id: 'compact',
  label: 'Compact',
  spaceScale: 0.875,
  radiusScale: 0,
});

export const ALL_DENSITIES = [comfortableDensity, compactDensity] as const;

export type DensityManifestEntry = {
  id: string;
  label: string;
  selector: string;
};

export const DENSITY_MANIFEST: readonly DensityManifestEntry[] = ALL_DENSITIES.map(
  ({ id, label, selector }) => ({ id, label, selector })
);

export type DensityId = (typeof ALL_DENSITIES)[number]['id'];
