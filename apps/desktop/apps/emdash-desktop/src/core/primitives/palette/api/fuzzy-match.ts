import type { PaletteMatchBand, PaletteRelevance } from './provider';

export interface PaletteTextFields {
  readonly primary: readonly string[];
  readonly secondary?: readonly string[];
}

const BAND_ORDER: Record<PaletteMatchBand, number> = {
  exact: 0,
  prefix: 1,
  substring: 2,
  fuzzy: 3,
  secondary: 4,
};

export function matchPaletteText(
  query: string,
  fields: PaletteTextFields
): PaletteRelevance | undefined {
  const normalizedQuery = normalize(query);
  if (!normalizedQuery) return undefined;

  const primary = bestMatch(normalizedQuery, fields.primary);
  if (primary) return primary;

  const secondary = bestMatch(normalizedQuery, fields.secondary ?? []);
  return secondary ? { band: 'secondary', score: secondary.score } : undefined;
}

function bestMatch(query: string, candidates: readonly string[]): PaletteRelevance | undefined {
  let best: PaletteRelevance | undefined;
  for (const value of candidates) {
    const match = matchCandidate(query, normalize(value));
    if (!match) continue;
    if (
      !best ||
      BAND_ORDER[match.band] < BAND_ORDER[best.band] ||
      (match.band === best.band && match.score > best.score)
    ) {
      best = match;
    }
  }
  return best;
}

function matchCandidate(query: string, candidate: string): PaletteRelevance | undefined {
  if (!candidate) return undefined;
  if (candidate === query) return { band: 'exact', score: 1 };
  if (candidate.startsWith(query)) {
    return { band: 'prefix', score: lengthScore(query, candidate) };
  }

  const substringIndex = candidate.indexOf(query);
  if (substringIndex !== -1) {
    const boundaryBonus = isBoundary(candidate, substringIndex) ? 0.1 : 0;
    return {
      band: 'substring',
      score: clamp(lengthScore(query, candidate) + boundaryBonus),
    };
  }

  let cursor = 0;
  let previous = -1;
  let boundaryMatches = 0;
  let consecutiveMatches = 0;
  let totalGap = 0;
  for (const character of query) {
    const index = candidate.indexOf(character, cursor);
    if (index === -1) return undefined;
    if (isBoundary(candidate, index)) boundaryMatches += 1;
    if (previous !== -1) {
      const gap = index - previous - 1;
      if (gap === 0) consecutiveMatches += 1;
      totalGap += gap;
    }
    previous = index;
    cursor = index + 1;
  }

  const boundaryScore = boundaryMatches / query.length;
  const consecutiveScore =
    query.length === 1 ? 0 : consecutiveMatches / Math.max(1, query.length - 1);
  const gapPenalty = totalGap / Math.max(1, candidate.length);
  const candidatePenalty = (candidate.length - query.length) / Math.max(1, candidate.length);

  return {
    band: 'fuzzy',
    score: clamp(
      0.35 +
        boundaryScore * 0.45 +
        consecutiveScore * 0.25 -
        gapPenalty * 0.1 -
        candidatePenalty * 0.1
    ),
  };
}

function normalize(value: string): string {
  return value.trim().toLocaleLowerCase().replace(/\s+/g, ' ');
}

function isBoundary(value: string, index: number): boolean {
  return index === 0 || /[\s/\\_.-]/.test(value[index - 1] ?? '');
}

function lengthScore(query: string, candidate: string): number {
  return clamp(0.5 + query.length / Math.max(1, candidate.length) / 2);
}

function clamp(value: number): number {
  return Math.max(0, Math.min(1, value));
}
