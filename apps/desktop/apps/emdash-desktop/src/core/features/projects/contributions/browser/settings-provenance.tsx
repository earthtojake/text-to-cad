import { Alert, Badge, Button } from '@emdash/ui/react/primitives';
import { RotateCcw } from 'lucide-react';
import type { Provenance } from '@core/primitives/project-settings/api';
import {
  brokenSettingText,
  provenanceBadgeLabel,
  provenanceSourceText,
  type ProvenanceFlavor,
} from './settings-provenance-labels';

/**
 * The one provenance → UI rendering layer (spec: github-git-settings §7, §9,
 * prototype Variant A): badges, source lines, broken-setting warnings, and
 * reset affordances for every surface that shows an effective value. Later
 * point-of-need surfaces (identity strips, worktree previews) build on these.
 * Text mappings live in `settings-provenance-labels.ts`.
 */

export function ProvenanceBadge({
  provenance,
  flavor = 'inferred',
}: {
  provenance: Provenance;
  flavor?: ProvenanceFlavor;
}) {
  const tone =
    provenance.kind === 'set'
      ? 'info'
      : provenance.kind === 'inferred'
        ? 'neutral'
        : provenance.kind === 'broken-setting'
          ? 'warning'
          : 'error';
  return (
    <Badge variant={provenance.kind === 'inferred' ? 'outline' : 'soft'} tone={tone}>
      {provenanceBadgeLabel(provenance, flavor)}
    </Badge>
  );
}

export function ProvenanceSourceLine({ provenance }: { provenance: Provenance }) {
  const text = provenanceSourceText(provenance);
  if (!text) return null;
  return <span className="text-xs text-foreground-muted">{text}</span>;
}

/** Warning for `broken-setting` provenance: the stale value plus the live fallback. */
export function BrokenSettingNotice({
  staleValue,
  effectiveValue,
}: {
  staleValue: string;
  effectiveValue: string | null;
}) {
  return (
    <Alert.Root status="warning">
      <Alert.Description>{brokenSettingText(staleValue, effectiveValue)}</Alert.Description>
    </Alert.Root>
  );
}

/** Per-field reset affordance: clearing the stored value returns it to inference. */
export function ResetProvenanceButton({
  flavor = 'inferred',
  onReset,
}: {
  flavor?: ProvenanceFlavor;
  onReset: () => void;
}) {
  return (
    <Button type="button" variant="ghost" size="xs" onClick={onReset}>
      <RotateCcw data-icon="inline-start" className="size-3" />
      {flavor === 'inherited' ? 'Reset to inherited' : 'Reset to inferred'}
    </Button>
  );
}
