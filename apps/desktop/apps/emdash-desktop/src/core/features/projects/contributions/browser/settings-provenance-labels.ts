import type { Provenance } from '@core/primitives/project-settings/api';

/**
 * Pure text mappings for the provenance → UI rendering layer
 * (spec: github-git-settings §7, §9). The components live in
 * `settings-provenance.tsx`; these are separate so they stay testable in the
 * node test project and reusable by non-React surfaces.
 */

/** Worktree root reads "Inherited" instead of "Inferred" (spec §9). */
export type ProvenanceFlavor = 'inferred' | 'inherited';

export function provenanceBadgeLabel(
  provenance: Provenance,
  flavor: ProvenanceFlavor = 'inferred'
): string {
  switch (provenance.kind) {
    case 'set':
      return 'Set';
    case 'inferred':
      return flavor === 'inherited' ? 'Inherited' : 'Inferred';
    case 'broken-setting':
      return 'Broken';
    case 'unresolvable':
      return 'Unavailable';
  }
}

/** Human labels for the resolver's inference sources. */
const SOURCE_LABELS: Record<string, string> = {
  'remote HEAD': 'from remote HEAD',
  'well-known remote branch': 'from a well-known remote branch',
  'well-known local branch': 'from a well-known local branch',
  'origin remote': 'from the origin remote',
  'sole remote': 'from the only remote',
  'first remote alphabetically': 'from the first remote',
  'base remote': 'from the base remote',
  'default account': 'from the default account',
  'only host-matching account': 'from the only matching account',
  'no host-matching account': 'no account matches this repository',
  'host default': 'from the host default',
  'built-in default': 'from the built-in default',
};

/** Source line for inferred values ("from remote HEAD"); null otherwise. */
export function provenanceSourceText(provenance: Provenance): string | null {
  if (provenance.kind !== 'inferred') return null;
  return SOURCE_LABELS[provenance.from] ?? `from ${provenance.from}`;
}

export function brokenSettingText(staleValue: string, effectiveValue: string | null): string {
  return effectiveValue === null
    ? `Set to '${staleValue}' — not found, and no fallback could be inferred.`
    : `Set to '${staleValue}' — not found, using '${effectiveValue}'.`;
}
